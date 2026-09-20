const {ipcRenderer} = require('electron');
window.addEventListener('DOMContentLoaded', () => {
  let clicks = 0;
  const snapshot = () => ipcRenderer.send('fixture-state', {
    entry:document.querySelector('#entry').value,
    multiline:document.querySelector('#multiline').value,
    secretLength:document.querySelector('#secret').value.length,
    selection:{start:document.querySelector('#multiline').selectionStart,end:document.querySelector('#multiline').selectionEnd},
    checked:document.querySelector('#check').checked, clicks
  });
  document.querySelector('#button').addEventListener('click', () => { clicks++;snapshot(); });
  document.addEventListener('input',snapshot);
  document.addEventListener('change',snapshot);
  document.addEventListener('selectionchange',snapshot);
  snapshot();
});
