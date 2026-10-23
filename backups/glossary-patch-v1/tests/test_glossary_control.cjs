const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

(async()=>{
  const nodes=new Map();
  const get=id=>{
    if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',disabled:false,
      addEventListener(type,fn){this[type]=fn;}});
    return nodes.get(id);
  };
  let fail=false,posts=[];
  const state={mode:'soft',effective_mode:'soft',generation:0,concepts:657,version:'medical-657-v1'};
  const ui={authorized:true,token:'test-token',localActive:false,directionId:'en-es',
    ready:Promise.resolve(),snapshot:{glossary:state,can_change_glossary:true},render(){},
    async refresh(){this.render();}};
  const context=vm.createContext({document:{getElementById:get},OperatorUI:ui,
    fetch:async(url,options)=>{
      const body=JSON.parse(options.body);posts.push({url,body});
      if(fail)return {ok:false};
      Object.assign(state,{mode:body.mode,effective_mode:body.mode,generation:state.generation+1});
      return {ok:true};
    }});
  vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../app/static/glossary_control.js'),'utf8'),context);
  await ui.ready;
  const select=get('glossary-mode'),info=get('glossary-info');
  assert.equal(select.disabled,false);assert.match(info.textContent,/657/);
  for(const mode of ['shadow','off','soft']){
    select.value=mode;await select.change();assert.equal(state.mode,mode);
  }
  assert.deepEqual(posts.map(p=>p.body.generation),[0,1,2]);
  ui.localActive=true;ui.render();assert.equal(select.disabled,true);
  const before=posts.length;await select.change();assert.equal(before,posts.length);
  ui.localActive=false;state.forced_by_environment=true;ui.render();assert.equal(select.disabled,true);
  state.forced_by_environment=false;ui.render();fail=true;
  select.value='off';await select.change();
  assert.equal(state.mode,'soft');assert.equal(select.value,'soft');
  assert.match(info.textContent,/No se pudo/);
  console.log('PASS: glossary selector changes, active-session lock, environment override and failed change');
})().catch(error=>{console.error(error);process.exitCode=1;});
