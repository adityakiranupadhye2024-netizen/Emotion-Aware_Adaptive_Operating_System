const {app,BrowserWindow}=require('electron'); const path=require('path');
function create(){const w=new BrowserWindow({width:1440,height:900,minWidth:1100,minHeight:700,backgroundColor:'#080b12',webPreferences:{contextIsolation:true}}); w.loadURL(process.env.EAOS_FRONTEND_URL||'http://127.0.0.1:5173');}
app.whenReady().then(create); app.on('window-all-closed',()=>{if(process.platform!=='darwin')app.quit()});
