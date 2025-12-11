console.log('Loading electron...');
const electron = require('electron');
console.log('Electron type:', typeof electron);
console.log('Electron keys:', Object.keys(electron || {}).slice(0, 20));

if (electron && electron.app) {
    console.log('Success! app exists');
    electron.app.on('ready', () => {
        console.log('App is ready!');
        electron.app.quit();
    });
} else {
    console.log('ERROR: app is', electron && electron.app);
    process.exit(1);
}
