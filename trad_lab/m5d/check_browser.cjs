/* Original renderer suites with a REMOTE location and asserted same-host sockets. */
'use strict';
const fs=require('fs'),path=require('path'),Module=require('module'),assert=require('node:assert/strict');
(async()=>{
  const copy=path.resolve(process.argv[2]);
  for(const name of ['test_overlay_renderer.cjs','test_overlay_geometry.cjs']){
    const filename=path.join(copy,'tests',name),m=new Module(filename,module);
    m.filename=filename;m.paths=Module._nodeModulePaths(path.dirname(filename));
    let source=fs.readFileSync(path.resolve('C:/live-captions/tests',name),'utf8');
    if(name==='test_overlay_renderer.cjs'){
      assert(source.includes("host:'localhost:8010'"));
      source=source.replace("host:'localhost:8010'","host:'192.168.50.10:3000'");
      source=source.replace('constructor() {this.readyState = 1;',"constructor(url) {assert.equal(url,'ws://192.168.50.10:3000/ws/overlay'); this.readyState = 1;");
    }
    m._compile(source,filename);await m.exports;
  }
  console.log('PASS: original renderer, remote same-host WS, DOM CLEAR, stale snapshots, pagination, reconnect bounds and geometry');
})().catch(error=>{console.error(error);process.exitCode=1;});
