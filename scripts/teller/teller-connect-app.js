// teller-connect-app.js
// Simple Express app to integrate Teller Connect and get access tokens

const express = require('express');
const axios = require('axios');
const fs = require('fs');
const https = require('https');
require('dotenv').config();

const app = express();
const PORT = 3000;

// Determine environment
const TELLER_ENV = process.env.TELLER_ENVIRONMENT || 'sandbox';
console.log(`\n🔧 Teller Environment: ${TELLER_ENV.toUpperCase()}`);

// Load Teller certificates for development/production
let httpsAgent = null;
if (TELLER_ENV !== 'sandbox') {
    if (process.env.TELLER_CERT_PATH && process.env.TELLER_KEY_PATH) {
        try {
            httpsAgent = new https.Agent({
                cert: fs.readFileSync(process.env.TELLER_CERT_PATH),
                key: fs.readFileSync(process.env.TELLER_KEY_PATH)
            });
            console.log('✅ Teller certificates loaded for development/production mode');
        } catch (error) {
            console.error('❌ Error loading certificates:', error.message);
            console.error('\nFor development/production mode, you need:');
            console.error('1. Download certificates from: https://teller.io/settings/certificates');
            console.error('2. Add to .env:');
            console.error('   TELLER_CERT_PATH=./certs/certificate.pem');
            console.error('   TELLER_KEY_PATH=./certs/private_key.pem');
            process.exit(1);
        }
    } else {
        console.error('❌ Certificates required for development/production mode!');
        console.error('\nAdd to your .env file:');
        console.error('TELLER_CERT_PATH=./certs/certificate.pem');
        console.error('TELLER_KEY_PATH=./certs/private_key.pem');
        console.error('\nOr switch to sandbox mode:');
        console.error('TELLER_ENVIRONMENT=sandbox');
        process.exit(1);
    }
} else {
    console.log('ℹ️  Running in sandbox mode (no certificates required)');
}

app.use(express.json());
app.use(express.static('public'));

// Serve the main page
app.get('/', (req, res) => {
    const environment = TELLER_ENV;
    const envInstructions = environment === 'sandbox'
        ? `<p><strong>Sandbox credentials:</strong></p>
       <ul>
         <li>Username: <code>username</code></li>
         <li>Password: <code>password</code></li>
       </ul>`
        : `<p><strong>Development mode:</strong> Use your real bank credentials</p>`;

    res.send(`
<!DOCTYPE html>
<html>
<head>
  <title>Teller Connect - Get Access Token</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      max-width: 800px;
      margin: 50px auto;
      padding: 20px;
      background: #f5f5f5;
    }
    .container {
      background: white;
      padding: 30px;
      border-radius: 8px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    h1 { color: #333; }
    button {
      background: #4CAF50;
      color: white;
      padding: 12px 24px;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      font-size: 16px;
    }
    button:hover { background: #45a049; }
    .info {
      background: #e3f2fd;
      padding: 15px;
      border-radius: 4px;
      margin: 20px 0;
    }
    .warning {
      background: #fff3cd;
      padding: 15px;
      border-radius: 4px;
      margin: 20px 0;
      border-left: 4px solid #ffc107;
    }
    .token {
      background: #f5f5f5;
      padding: 15px;
      border-radius: 4px;
      word-break: break-all;
      font-family: monospace;
      margin: 10px 0;
    }
    .success {
      background: #4CAF50;
      color: white;
      padding: 15px;
      border-radius: 4px;
      margin: 20px 0;
    }
    .env-badge {
      display: inline-block;
      padding: 5px 10px;
      border-radius: 4px;
      font-weight: bold;
      margin-bottom: 10px;
      ${environment === 'sandbox' ? 'background: #2196F3; color: white;' : 'background: #ff9800; color: white;'}
    }
  </style>
  <script src="https://cdn.teller.io/connect/connect.js"></script>
</head>
<body>
  <div class="container">
    <div class="env-badge">Environment: ${environment.toUpperCase()}</div>
    <h1>🏦 Teller Connect - Get Access Token</h1>
    
    ${environment === 'development' ? `
    <div class="warning">
      <strong>⚠️  Development Mode Active</strong>
      <p>You're connecting to REAL bank accounts. Make sure:</p>
      <ul>
        <li>Certificates are properly configured</li>
        <li>You're using production Teller application ID</li>
        <li>You understand this will access real financial data</li>
      </ul>
    </div>
    ` : ''}
    
    <div class="info">
      <h3>📋 Instructions:</h3>
      <ol>
        <li>Click "Connect Bank Account" below</li>
        <li>Select your bank</li>
        ${envInstructions}
        <li>Your access token will appear below - it's automatically saved</li>
      </ol>
    </div>

    <button id="connectButton">Connect Bank Account</button>
    
    <div id="result"></div>
  </div>

  <script>
    const APP_ID = '${process.env.TELLER_APP_ID || 'YOUR_APP_ID'}';
    const ENVIRONMENT = '${environment}';
    
    const tellerConnect = TellerConnect.setup({
      applicationId: APP_ID,
      environment: ENVIRONMENT,
      onSuccess: async (enrollment) => {
        console.log('Enrollment success:', enrollment);
        
        const resultDiv = document.getElementById('result');
        resultDiv.innerHTML = \`
          <div class="success">
            <h3>✅ Success! Bank Account Connected</h3>
            <p><strong>Enrollment ID:</strong> \${enrollment.enrollment.id}</p>
            <p><strong>Access Token:</strong></p>
            <div class="token">\${enrollment.accessToken}</div>
            <p><strong>Institution:</strong> \${enrollment.enrollment.institution.name}</p>
            <p><strong>Environment:</strong> ${environment}</p>
          </div>
          
          <div class="info">
            <h4>✅ Token Automatically Saved!</h4>
            <p>The token has been added to your .env file and backed up to teller-tokens.log</p>
            <p><strong>Next steps:</strong></p>
            <ol>
              <li>You can connect more accounts by clicking "Connect Bank Account" again</li>
              <li>Or close this and run: <code>node index.js test</code></li>
            </ol>
          </div>
        \`;
        
        // Send to backend to save
        try {
          const response = await fetch('/save-token', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              accessToken: enrollment.accessToken,
              enrollmentId: enrollment.enrollment.id,
              environment: ENVIRONMENT
            })
          });
          
          const data = await response.json();
          console.log('Token saved, total tokens:', data.totalTokens);
        } catch (error) {
          console.error('Error saving token:', error);
        }
      },
      onExit: () => {
        console.log('User exited Teller Connect');
      }
    });

    document.getElementById('connectButton').addEventListener('click', () => {
      tellerConnect.open();
    });
  </script>
</body>
</html>
  `);
});

// Endpoint to save the access token
app.post('/save-token', (req, res) => {
    const { accessToken, enrollmentId, environment } = req.body;

    console.log('\n✅ New Access Token Received!');
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.log('Access Token:', accessToken);
    console.log('Enrollment ID:', enrollmentId);
    console.log('Environment:', environment || 'sandbox');
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n');

    // Read existing .env file
    let envContent = '';
    let existingTokens = [];

    if (fs.existsSync('.env')) {
        envContent = fs.readFileSync('.env', 'utf8');
        const tokenMatch = envContent.match(/TELLER_API_KEY=([^\n]+)/);

        if (tokenMatch) {
            existingTokens = tokenMatch[1].split(',').map(t => t.trim());

            // Check if token already exists
            if (!existingTokens.includes(accessToken)) {
                existingTokens.push(accessToken);

                // Update the .env file
                const newTokenLine = `TELLER_API_KEY=${existingTokens.join(',')}`;
                envContent = envContent.replace(/TELLER_API_KEY=[^\n]+/, newTokenLine);

                fs.writeFileSync('.env', envContent);

                console.log('✅ Token added to .env file');
                console.log(`📊 Total tokens: ${existingTokens.length}\n`);
            } else {
                console.log('ℹ️  Token already exists in .env file\n');
            }
        } else {
            // TELLER_API_KEY doesn't exist, add it
            envContent += `\n# Teller Access Tokens\nTELLER_API_KEY=${accessToken}\n`;
            fs.writeFileSync('.env', envContent);
            console.log('✅ Token added to .env file\n');
            existingTokens.push(accessToken);
        }
    } else {
        console.log('⚠️  .env file not found, creating new one...');
        envContent = `TELLER_API_KEY=${accessToken}\nTELLER_ENVIRONMENT=${environment || 'sandbox'}\n`;
        fs.writeFileSync('.env', envContent);
        console.log('✅ Created .env file with token\n');
        existingTokens.push(accessToken);
    }

    // Also append to tokens log file for backup
    const logEntry = `${new Date().toISOString()} | Env: ${environment || 'sandbox'} | Enrollment: ${enrollmentId} | Token: ${accessToken}\n`;
    fs.appendFileSync('teller-tokens.log', logEntry);
    console.log('💾 Token backed up to teller-tokens.log\n');

    console.log('Current tokens in .env:');
    existingTokens.forEach((token, i) => {
        const masked = `${token.substring(0, 8)}...${token.substring(token.length - 4)}`;
        console.log(`  ${i + 1}. ${masked}`);
    });
    console.log('');

    res.json({ success: true, totalTokens: existingTokens.length });
});

// Test endpoint to verify token works
app.get('/test-token', async (req, res) => {
    const token = req.query.token || process.env.TELLER_API_KEY;

    if (!token) {
        return res.status(400).json({ error: 'No token provided' });
    }

    try {
        const requestConfig = {
            auth: {
                username: token,
                password: ''
            }
        };

        if (httpsAgent) {
            requestConfig.httpsAgent = httpsAgent;
        }

        const response = await axios.get('https://api.teller.io/accounts', requestConfig);

        res.json({
            success: true,
            environment: TELLER_ENV,
            accounts: response.data.length,
            data: response.data
        });
    } catch (error) {
        res.status(error.response?.status || 500).json({
            success: false,
            error: error.message,
            details: error.response?.data
        });
    }
});

// Start server
app.listen(PORT, () => {
    console.log('\n🚀 Teller Connect App Running!');
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.log(`📱 Open: http://localhost:${PORT}`);
    console.log(`🌍 Environment: ${TELLER_ENV.toUpperCase()}`);
    if (TELLER_ENV !== 'sandbox') {
        console.log(`🔐 Certificates: ${httpsAgent ? 'Loaded ✅' : 'Not loaded ❌'}`);
    }
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n');

    if (TELLER_ENV === 'sandbox') {
        console.log('Instructions:');
        console.log('1. Click "Connect Bank Account"');
        console.log('2. Use sandbox credentials:');
        console.log('   Username: username');
        console.log('   Password: password');
        console.log('3. Your access token will be saved automatically\n');
    } else {
        console.log('Instructions:');
        console.log('1. Click "Connect Bank Account"');
        console.log('2. Select your real bank');
        console.log('3. Log in with your actual credentials');
        console.log('4. Complete any MFA challenges');
        console.log('5. Your access token will be saved automatically\n');
    }
});