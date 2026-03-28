require('dotenv').config();
const { google } = require('googleapis');
const axios = require('axios');
const cron = require('node-cron');
const fs = require('fs');
const https = require('https');

// Validate environment variables first
if (!process.env.GOOGLE_CREDENTIALS) {
    console.error('ERROR: GOOGLE_CREDENTIALS environment variable is not set');
    console.error('Please check your .env file exists and contains GOOGLE_CREDENTIALS');
    process.exit(1);
}

let googleCredentials;
try {
    googleCredentials = JSON.parse(process.env.GOOGLE_CREDENTIALS);

    // Fix the private key format - replace \\n with actual newlines
    if (googleCredentials.private_key) {
        googleCredentials.private_key = googleCredentials.private_key.replace(/\\n/g, '\n');
    }
} catch (error) {
    console.error('ERROR: Failed to parse GOOGLE_CREDENTIALS JSON');
    console.error('Make sure your .env file has properly formatted JSON on a single line');
    console.error('Error details:', error.message);
    process.exit(1);
}

// Load Teller certificates if provided
let httpsAgent = null;
if (process.env.TELLER_CERT_PATH && process.env.TELLER_KEY_PATH) {
    try {
        httpsAgent = new https.Agent({
            cert: fs.readFileSync(process.env.TELLER_CERT_PATH),
            key: fs.readFileSync(process.env.TELLER_KEY_PATH)
        });
        console.log('✅ Teller certificates loaded successfully');
    } catch (error) {
        console.error('⚠️  Warning: Could not load Teller certificates:', error.message);
        console.error('For sandbox mode without real data, certificates are optional.');
        console.error('For production, download certificates from: https://teller.io/settings/certificates');
    }
}

// Configuration
const config = {
    teller: {
        // Support multiple access tokens (comma-separated in env var)
        apiKeys: process.env.TELLER_API_KEY.split(',').map(key => key.trim()),
        baseUrl: 'https://api.teller.io',
        httpsAgent: httpsAgent
    },
    google: {
        credentials: googleCredentials,
        spreadsheetId: process.env.SPREADSHEET_ID,
        sheetName: 'Transactions' // Default, will be overridden with month-specific name
    }
};

// Generate sheet name based on year and month
function generateSheetName(year, month) {
    return `Transactions ${year}-${month.toString().padStart(2, '0')}`;
}

// Initialize Google Sheets API with JWT
async function getGoogleSheetsClient() {
    try {
        const auth = new google.auth.JWT({
            email: config.google.credentials.client_email,
            key: config.google.credentials.private_key,
            scopes: ['https://www.googleapis.com/auth/spreadsheets']
        });

        await auth.authorize();
        return google.sheets({ version: 'v4', auth });
    } catch (error) {
        console.error('Google Sheets authentication error:', error.message);
        throw error;
    }
}

// Fetch accounts from Teller
async function getTellerAccounts(apiKey) {
    try {
        const requestConfig = {
            auth: {
                username: apiKey,
                password: ''
            },
            headers: {
                'Accept': 'application/json'
            }
        };

        // Add HTTPS agent with certificates if available
        if (config.teller.httpsAgent) {
            requestConfig.httpsAgent = config.teller.httpsAgent;
        }

        const response = await axios.get(`${config.teller.baseUrl}/accounts`, requestConfig);
        return response.data;
    } catch (error) {
        console.error('Error fetching Teller accounts:', error.message);

        if (error.response) {
            console.error('Status:', error.response.status);
            console.error('Error details:', error.response.data);

            if (error.response.status === 400) {
                console.error('\n⚠️  Authentication Error!');
                console.error('Your Teller API key appears to be invalid or you need an access token.');
                console.error('\nTeller requires an ACCESS TOKEN, not an Application ID.');
                console.error('You need to:');
                console.error('1. Use Teller Connect to link a bank account first');
                console.error('2. Get an access_token from the enrollment process');
                console.error('3. Use that access_token as your TELLER_API_KEY');
                console.error('\nFor testing, you can use Teller\'s sandbox mode:');
                console.error('- Username: username');
                console.error('- Password: password');
                console.error('- Access token will be generated after enrollment');
            }
        } else if (error.code === 'UNABLE_TO_VERIFY_LEAF_SIGNATURE' ||
            error.code === 'CERT_HAS_EXPIRED' ||
            error.message.includes('certificate')) {
            console.error('\n⚠️  Certificate Error!');
            console.error('Teller requires client certificates for authentication.');
            console.error('\nTo fix this:');
            console.error('1. Download your certificates from: https://teller.io/settings/certificates');
            console.error('2. Extract teller.zip to get certificate.pem and private_key.pem');
            console.error('3. Add these to your .env file:');
            console.error('   TELLER_CERT_PATH=./certs/certificate.pem');
            console.error('   TELLER_KEY_PATH=./certs/private_key.pem');
        }

        throw error;
    }
}

// Fetch all accounts from all access tokens
async function getAllTellerAccounts() {
    const allAccounts = [];

    console.log(`Fetching accounts from ${config.teller.apiKeys.length} access token(s)...`);

    for (let i = 0; i < config.teller.apiKeys.length; i++) {
        const apiKey = config.teller.apiKeys[i];
        const maskedKey = `${apiKey.substring(0, 8)}...${apiKey.substring(apiKey.length - 4)}`;

        try {
            console.log(`  Checking token ${i + 1}/${config.teller.apiKeys.length} (${maskedKey})`);
            const accounts = await getTellerAccounts(apiKey);

            // Add the API key to each account so we know which token to use for transactions
            accounts.forEach(account => {
                account._tellerApiKey = apiKey;
            });

            allAccounts.push(...accounts);
            console.log(`    ✅ Found ${accounts.length} account(s)`);
        } catch (error) {
            console.error(`    ❌ Failed to fetch accounts from token ${i + 1}: ${error.message}`);
            // Continue with other tokens
        }
    }

    return allAccounts;
}

// Fetch transactions from Teller for a specific account
async function getTellerTransactions(account, fromDate, toDate) {
    try {
        const requestConfig = {
            auth: {
                username: account._tellerApiKey, // Use the API key associated with this account
                password: ''
            }
        };

        // Add HTTPS agent with certificates if available
        if (config.teller.httpsAgent) {
            requestConfig.httpsAgent = config.teller.httpsAgent;
        }

        // Teller API returns all transactions, we need to filter client-side
        const response = await axios.get(
            `${config.teller.baseUrl}/accounts/${account.id}/transactions`,
            requestConfig
        );

        // Filter transactions by date range
        const filteredTransactions = response.data.filter(txn => {
            const txnDate = txn.date; // Format: YYYY-MM-DD
            return txnDate >= fromDate && txnDate <= toDate;
        });

        return filteredTransactions;
    } catch (error) {
        // Check for enrollment status in headers
        const enrollmentStatus = error.response?.headers?.[`teller-enrollment-status`];

        if (error.response?.status === 404 && enrollmentStatus) {
            console.error(`  ⚠️  Account disconnected: ${enrollmentStatus}`);

            if (enrollmentStatus.includes('mfa_required')) {
                console.error(`  ℹ️  MFA required - please reconnect this account using Teller Connect`);
            } else if (enrollmentStatus.includes('disconnected')) {
                console.error(`  ℹ️  Account disconnected - please reconnect using Teller Connect`);
            }

            console.error(`  Account: ${account.name} (${account.institution.name})`);
            console.error(`  Account ID: ${account.id}`);
            console.error(`  🔄 To fix: Run 'node teller-connect-app.js' and reconnect this bank\n`);

            // Return empty array instead of throwing - continue with other accounts
            return [];
        }

        console.error(`  ❌ Error fetching transactions for account ${account.id}:`, error.message);

        // For other errors, return empty array to continue processing
        return [];
    }
}

// Get date range for previous month
function getPreviousMonthDateRange() {
    const now = new Date();
    const firstDayPrevMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const lastDayPrevMonth = new Date(now.getFullYear(), now.getMonth(), 0);

    return {
        fromDate: firstDayPrevMonth.toISOString().split('T')[0],
        toDate: lastDayPrevMonth.toISOString().split('T')[0],
        monthName: firstDayPrevMonth.toLocaleString('default', { month: 'long', year: 'numeric' }),
        year: firstDayPrevMonth.getFullYear(),
        month: firstDayPrevMonth.getMonth() + 1
    };
}

// Get date range for a specific month (for testing)
function getMonthDateRange(year, month) {
    const firstDay = new Date(year, month - 1, 1);
    const lastDay = new Date(year, month, 0);

    return {
        fromDate: firstDay.toISOString().split('T')[0],
        toDate: lastDay.toISOString().split('T')[0],
        monthName: firstDay.toLocaleString('default', { month: 'long', year: 'numeric' }),
        year: year,
        month: month
    };
}

// Format transactions for Google Sheets
function formatTransactionsForSheets(transactions, accountName) {
    return transactions.map(txn => [
        txn.date,
        accountName,
        txn.description,
        txn.amount,
        txn.status,
        txn.type,
        txn.id
    ]);
}

// Update Google Sheets with transactions
async function updateGoogleSheets(transactions, sheetName) {
    const sheets = await getGoogleSheetsClient();
    const spreadsheetId = config.google.spreadsheetId;

    console.log(`\nUpdating sheet: "${sheetName}"`);

    try {
        // Get spreadsheet info
        const spreadsheet = await sheets.spreadsheets.get({ spreadsheetId });

        // Check if the specific month sheet exists
        const sheetExists = spreadsheet.data.sheets.some(
            sheet => sheet.properties.title === sheetName
        );

        // Create sheet if it doesn't exist
        if (!sheetExists) {
            console.log(`Creating new sheet: ${sheetName}`);
            await sheets.spreadsheets.batchUpdate({
                spreadsheetId,
                requestBody: {
                    requests: [{
                        addSheet: {
                            properties: {
                                title: sheetName
                            }
                        }
                    }]
                }
            });
            console.log(`✅ Sheet "${sheetName}" created successfully`);
        }

        // Add headers if sheet is empty or newly created
        const headersRange = `${sheetName}!A1:G1`;
        const headers = [['Date', 'Account', 'Description', 'Amount', 'Status', 'Type', 'Transaction ID']];

        try {
            const existingData = await sheets.spreadsheets.values.get({
                spreadsheetId,
                range: headersRange
            });

            // If no data or headers don't match, add headers
            if (!existingData.data.values || existingData.data.values.length === 0) {
                await sheets.spreadsheets.values.update({
                    spreadsheetId,
                    range: headersRange,
                    valueInputOption: 'RAW',
                    requestBody: { values: headers }
                });
                console.log('✅ Headers added to sheet');
            }
        } catch (error) {
            // If get fails, sheet is empty, add headers
            await sheets.spreadsheets.values.update({
                spreadsheetId,
                range: headersRange,
                valueInputOption: 'RAW',
                requestBody: { values: headers }
            });
            console.log('✅ Headers added to sheet');
        }

        // Get all existing transactions to check for duplicates
        console.log('Checking for existing transactions...');
        let existingTransactions = new Set();

        try {
            const allDataRange = `${sheetName}!A2:G`; // Skip header row
            const existingDataResponse = await sheets.spreadsheets.values.get({
                spreadsheetId,
                range: allDataRange
            });

            if (existingDataResponse.data.values) {
                // Create a Set of transaction IDs for fast lookup
                existingDataResponse.data.values.forEach(row => {
                    if (row[6]) { // Transaction ID is in column G (index 6)
                        existingTransactions.add(row[6]);
                    }
                });
                console.log(`Found ${existingTransactions.size} existing transactions in sheet`);
            }
        } catch (error) {
            // No existing data, continue
            console.log('No existing transactions found in this sheet');
        }

        // Filter out duplicates
        const newTransactions = transactions.filter(txn => {
            const transactionId = txn[6]; // Transaction ID is last column
            return !existingTransactions.has(transactionId);
        });

        console.log(`Original transactions: ${transactions.length}`);
        console.log(`Duplicates found: ${transactions.length - newTransactions.length}`);
        console.log(`New transactions to add: ${newTransactions.length}`);

        // Append only new transactions
        if (newTransactions.length > 0) {
            const range = `${sheetName}!A:G`;
            await sheets.spreadsheets.values.append({
                spreadsheetId,
                range,
                valueInputOption: 'RAW',
                insertDataOption: 'INSERT_ROWS',
                requestBody: { values: newTransactions }
            });

            console.log(`✅ Added ${newTransactions.length} new transactions to "${sheetName}"`);
        } else {
            console.log(`ℹ️  No new transactions to add to "${sheetName}" (all transactions already exist)`);
        }

    } catch (error) {
        console.error('Error updating Google Sheets:', error.message);
        if (error.code === 404) {
            console.error('❌ Spreadsheet not found. Please check your SPREADSHEET_ID');
        } else if (error.code === 403) {
            console.error('❌ Permission denied. Make sure you shared the spreadsheet with:');
            console.error(`   ${config.google.credentials.client_email}`);
        }
        throw error;
    }
}

// Main function to sync transactions
async function syncTransactions(year = null, month = null) {
    console.log('Starting transaction sync...');

    try {
        // Get date range for previous month or specified month
        let dateRange;
        if (year && month) {
            dateRange = getMonthDateRange(year, month);
            console.log(`Fetching transactions for ${dateRange.monthName}`);
        } else {
            dateRange = getPreviousMonthDateRange();
            console.log(`Fetching transactions for previous month: ${dateRange.monthName}`);
        }

        const { fromDate, toDate, monthName } = dateRange;
        console.log(`Date range: ${fromDate} to ${toDate}`);

        // Generate sheet name based on year and month
        const sheetName = generateSheetName(dateRange.year, dateRange.month);
        console.log(`Sheet name: "${sheetName}"\n`);

        // Fetch all accounts from all access tokens
        const accounts = await getAllTellerAccounts();
        console.log(`\nTotal accounts found: ${accounts.length}`);

        if (accounts.length === 0) {
            console.warn('⚠️  No accounts found. Make sure your access tokens are correct.');
            return;
        }

        let allTransactions = [];
        let successfulAccounts = 0;
        let failedAccounts = 0;
        let disconnectedAccounts = [];

        // Fetch transactions for each account
        for (const account of accounts) {
            console.log(`Fetching transactions for account: ${account.name} (${account.institution.name})`);
            const transactions = await getTellerTransactions(account, fromDate, toDate);

            if (transactions.length === 0 && account.status !== 'closed') {
                // Account might be disconnected or has no transactions
                const statusCheck = await checkAccountStatus(account);
                if (statusCheck === 'disconnected') {
                    failedAccounts++;
                    disconnectedAccounts.push({
                        name: account.name,
                        institution: account.institution.name,
                        id: account.id
                    });
                }
            }

            console.log(`  Found ${transactions.length} transactions`);

            if (transactions.length > 0) {
                successfulAccounts++;
                const formattedTransactions = formatTransactionsForSheets(
                    transactions,
                    account.name
                );
                allTransactions = allTransactions.concat(formattedTransactions);
            }
        }

        console.log(`\n📊 Summary:`);
        console.log(`   Total accounts: ${accounts.length}`);
        console.log(`   Successful: ${successfulAccounts}`);
        console.log(`   Failed/Disconnected: ${failedAccounts}`);
        console.log(`   Total transactions to sync: ${allTransactions.length}`);

        // Show disconnected accounts summary
        if (disconnectedAccounts.length > 0) {
            console.log(`\n⚠️  Disconnected Accounts (need reconnection):`);
            disconnectedAccounts.forEach((acc, i) => {
                console.log(`   ${i + 1}. ${acc.name} (${acc.institution})`);
            });
            console.log(`\n🔄 To reconnect: Run 'node teller-connect-app.js'\n`);
        }

        // Update Google Sheets with month-specific sheet name
        if (allTransactions.length > 0) {
            await updateGoogleSheets(allTransactions, sheetName);

            console.log(`\n✅ Transaction sync completed successfully for ${monthName}`);
            console.log(`   Sheet: "${sheetName}"`);
            console.log(`   Total: ${allTransactions.length} transactions processed`);
        } else {
            console.log(`\nℹ️  No transactions to sync for ${monthName}`);
        }

        if (disconnectedAccounts.length > 0) {
            console.log(`\n⚠️  Warning: ${disconnectedAccounts.length} account(s) need to be reconnected`);
        }

    } catch (error) {
        console.error('Error during transaction sync:', error);
        throw error;
    }
}

// Helper function to check account status
async function checkAccountStatus(account) {
    try {
        const requestConfig = {
            auth: {
                username: account._tellerApiKey,
                password: ''
            }
        };

        if (config.teller.httpsAgent) {
            requestConfig.httpsAgent = config.teller.httpsAgent;
        }

        await axios.get(
            `${config.teller.baseUrl}/accounts/${account.id}`,
            requestConfig
        );

        return 'connected';
    } catch (error) {
        const enrollmentStatus = error.response?.headers?.['teller-enrollment-status'];
        if (enrollmentStatus && enrollmentStatus.includes('disconnected')) {
            return 'disconnected';
        }
        return 'error';
    }
}

// Schedule the job to run at the end of every month (1st day at 1 AM)
function scheduleMonthlySync() {
    // Runs at 1:00 AM on the 1st of every month
    cron.schedule('0 1 1 * *', async () => {
        console.log('Running scheduled monthly transaction sync');
        try {
            await syncTransactions();
        } catch (error) {
            console.error('Scheduled sync failed:', error);
        }
    });

    console.log('Monthly sync scheduled: 1st of every month at 1:00 AM');
}

// Start the service
async function start() {
    console.log('Teller to Google Sheets Service starting...');

    // Validate required environment variables
    const requiredEnvVars = ['TELLER_API_KEY', 'GOOGLE_CREDENTIALS', 'SPREADSHEET_ID'];
    const missingVars = requiredEnvVars.filter(varName => !process.env[varName]);

    if (missingVars.length > 0) {
        console.error(`Missing required environment variables: ${missingVars.join(', ')}`);
        process.exit(1);
    }

    // Schedule monthly sync
    scheduleMonthlySync();

    // Optional: Run immediately for testing (comment out in production)
    // Uncomment the line below ONLY if you want to test immediately
    // await syncTransactions();

    console.log('Service started successfully');
    console.log('\n📅 Scheduled to run on the 1st of every month at 1:00 AM');
    console.log('💡 To test immediately, uncomment the syncTransactions() line in the start() function');
}

// Handle graceful shutdown
process.on('SIGINT', () => {
    console.log('Service shutting down...');
    process.exit(0);
});

// Start the service
start().catch(error => {
    console.error('Failed to start service:', error);
    process.exit(1);
});

// Start the service
module.exports = { syncTransactions, scheduleMonthlySync };

// Handle command line arguments for testing
if (require.main === module) {
    const args = process.argv.slice(2);

    if (args.length === 0) {
        // Normal service mode - schedule monthly sync
        start().catch(error => {
            console.error('Failed to start service:', error);
            process.exit(1);
        });
    } else if (args[0] === 'test') {
        // Test mode - run immediately for previous month
        console.log('🧪 TEST MODE: Running sync for previous month');
        syncTransactions().then(() => {
            console.log('\n✅ Test completed successfully');
            process.exit(0);
        }).catch(error => {
            console.error('Test failed:', error);
            process.exit(1);
        });
    } else if (args[0] === 'month' && args.length === 3) {
        // Specific month mode - run for specified year and month
        const year = parseInt(args[1]);
        const month = parseInt(args[2]);

        if (isNaN(year) || isNaN(month) || month < 1 || month > 12) {
            console.error('Invalid year or month. Usage: node index.js month YYYY MM');
            process.exit(1);
        }

        console.log(`🧪 TEST MODE: Running sync for ${year}-${month.toString().padStart(2, '0')}`);
        syncTransactions(year, month).then(() => {
            console.log('\n✅ Test completed successfully');
            process.exit(0);
        }).catch(error => {
            console.error('Test failed:', error);
            process.exit(1);
        });
    } else {
        console.log('Usage:');
        console.log('  node index.js              # Start service (scheduled mode)');
        console.log('  node index.js test         # Test sync for previous month');
        console.log('  node index.js month YYYY MM  # Test sync for specific month');
        console.log('\nExamples:');
        console.log('  node index.js test         # Sync September 2025 transactions');
        console.log('  node index.js month 2025 9 # Sync September 2025 transactions');
        process.exit(0);
    }
}