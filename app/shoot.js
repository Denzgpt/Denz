// Screenshot each group tab of demo/artifact.html (daily bars) into demo/charts/*.png
const {chromium}=require('playwright');const fs=require('fs'),path=require('path');
(async()=>{const root=path.resolve(__dirname,'..');const html=fs.readFileSync(path.join(root,'demo','artifact.html'),'utf8');
const tmp='/tmp/claude-0/shoot.html';fs.writeFileSync(tmp,'<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">'+html);
const b=await chromium.launch();const p=await b.newPage({viewport:{width:1100,height:900},deviceScaleFactor:1.5});await p.goto('file://'+tmp);await p.waitForTimeout(2500);
const tabs=await p.$$eval('#tabs button',bs=>bs.map(x=>x.textContent));
for(const t of tabs){await p.click(`#tabs button:has-text("${t.split(' · ')[0]}")`);await p.waitForTimeout(1500);
 const name=t.split(' · ')[0].replace(/[^A-Za-z]+/g,'_');const el=await p.$('main');await el.screenshot({path:path.join(root,'demo','charts',name+'.png')})}
await b.close();console.log(tabs)})()
