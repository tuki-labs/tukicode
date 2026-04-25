#!/usr/bin/env node

/**
 * TukiCode NPM Bridge
 * This script allows calling the 'tuki' command (installed via pip) 
 * from the npm global bin.
 */

const { spawn } = require('child_process');
const path = require('path');

// We simply spawn the 'tuki' command that should be in the PATH after pip installation
const child = spawn('tuki', process.argv.slice(2), {
    stdio: 'inherit',
    shell: true
});

child.on('exit', (code) => {
    process.exit(code);
});

child.on('error', (err) => {
    console.error('Error: Could not execute "tuki". Make sure TukiCode is installed via pip.');
    console.error(err.message);
    process.exit(1);
});
