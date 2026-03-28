// setup-env.js
// Helper script to create properly formatted .env file

const fs = require('fs');
const readline = require('readline');

const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

function question(query) {
    return new Promise(resolve => rl.question(query, resolve));
}

async function setup() {
    console.log('=== Teller to Google Sheets - Environment Setup ===\n');

    // Get Teller API Key
    const tellerApiKey = await question('Enter your Teller Access Token (from Teller Connect): ');

    // Get Teller App ID
    const tellerAppId = await question('Enter your Teller Application ID (starts with app_): ');

    // Get Certificate paths
    const certPath = await question('Enter path to Teller certificate.pem (or press Enter to skip): ');
    const keyPath = certPath ? await question('Enter path to Teller private_key.pem: ') : '';

    // Get Spreadsheet ID
    console.log('\nGet your Spreadsheet ID from the URL:');
    console.log('https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit\n');
    const spreadsheetId = await question('Enter your Spreadsheet ID: ');

    // Get Google Credentials
    console.log('\nEnter the path to your Google Service Account JSON file:');
    const credentialsPath = await question('Path: ');

    let googleCredentials;
    try {
        const credentialsContent = fs.readFileSync(credentialsPath.trim(), 'utf8');
        googleCredentials = JSON.parse(credentialsContent);

        // IMPORTANT: Convert newlines to \\n (double backslash) for .env file
        // The code will convert \\n back to actual newlines when parsing
        googleCredentials.private_key = googleCredentials.private_key.replace(/\n/g, '\\n');
        const credentialsString = JSON.stringify(googleCredentials);

        // Create .env file content
        let envContent = `# Teller API Configuration
TELLER_API_KEY=${tellerApiKey.trim()}
TELLER_APP_ID=${tellerAppId.trim()}
`;

        if (certPath && keyPath) {
            envContent += `TELLER_CERT_PATH=${certPath.trim()}
TELLER_KEY_PATH=${keyPath.trim()}
`;
        }

        envContent += `
# Google Sheets Configuration
SPREADSHEET_ID=${spreadsheetId.trim()}

# Google Service Account Credentials (do not modify this line)
GOOGLE_CREDENTIALS=${credentialsString}
`;

        // Write .env file
        fs.writeFileSync('.env', envContent);

        console.log('\n✅ .env file created successfully!');
        console.log('\nYou can now run:');
        console.log('  node index.js           # To start the service');
        console.log('  docker build -t teller-sheets-sync .   # To build Docker image');
        console.log('  docker run -d --env-file .env teller-sheets-sync   # To run in Docker');

        // Test Google credentials
        console.log('\n🧪 Testing Google credentials format...');
        const testParse = JSON.parse(credentialsString);
        if (testParse.private_key.includes('\\n')) {
            console.log('✅ Private key format is correct');
        } else {
            console.log('⚠️  Warning: Private key might not be formatted correctly');
        }

    } catch (error) {
        console.error('\n❌ Error:', error.message);
        console.log('\nMake sure:');
        console.log('1. The credentials file path is correct');
        console.log('2. The JSON file is valid');
    }

    rl.close();
}

// Alternative: Direct conversion function if you already have the JSON
function convertJsonToEnvFormat(jsonFilePath) {
    try {
        const content = fs.readFileSync(jsonFilePath, 'utf8');
        const json = JSON.parse(content);

        // Escape newlines in private_key - use double backslash for .env file
        json.private_key = json.private_key.replace(/\n/g, '\\n');

        // Output single-line JSON
        const singleLine = JSON.stringify(json);
        console.log('\nCopy this line to your .env file:');
        console.log(`GOOGLE_CREDENTIALS=${singleLine}`);

        return singleLine;
    } catch (error) {
        console.error('Error:', error.message);
    }
}

// Run setup if called directly
if (require.main === module) {
    setup().catch(console.error);
}

module.exports = { convertJsonToEnvFormat };