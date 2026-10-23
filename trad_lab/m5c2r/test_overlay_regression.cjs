/* Run existing renderer/transport assertions against the repaired COPY assets. */
'use strict';
const fs=require('fs'),path=require('path'),Module=require('module');
(async()=>{
  const copy=path.resolve(process.argv[2]);
  for(const name of ['test_overlay_renderer.cjs','test_overlay_geometry.cjs']){
    const virtual=path.join(copy,'tests',name),m=new Module(virtual,module);
    m.filename=virtual;m.paths=Module._nodeModulePaths(path.dirname(virtual));
    m._compile(fs.readFileSync(path.resolve('tests',name),'utf8'),virtual);
    await m.exports;
  }
  console.log('PASS: existing overlay renderer/WebSocket/geometry regressions against repaired copy');
})().catch(e=>{console.error(e);process.exitCode=1;});
