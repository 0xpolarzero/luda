const {app, BrowserWindow, ipcMain} = require('electron');
const fs = require('node:fs');
const path = require('node:path');
app.setPath('userData', process.env.LUDA_ELECTRON_PROFILE);
const enabled = process.env.LUDA_ELECTRON_ACCESSIBILITY !== '0';
app.commandLine.appendSwitch(enabled ? 'force-renderer-accessibility' : 'disable-renderer-accessibility');
app.commandLine.appendSwitch('host-resolver-rules', 'MAP * 0.0.0.0');
app.whenReady().then(() => {
  app.setAccessibilitySupportEnabled(enabled);
  ipcMain.on('fixture-state', (_event, state) => {
    const target = process.env.LUDA_ELECTRON_ORACLE;
    fs.writeFileSync(target + '.next', JSON.stringify({...state, versions:process.versions, accessibility:app.isAccessibilitySupportEnabled()}));
    fs.renameSync(target + '.next', target);
  });
  const win = new BrowserWindow({width:900,height:700,title:'Luda Electron Fixture',webPreferences:{preload:path.join(__dirname,'preload.js'),contextIsolation:true,nodeIntegration:false}});
  win.loadFile(path.join(__dirname,'index.html'));
});
app.on('window-all-closed',()=>app.quit());
