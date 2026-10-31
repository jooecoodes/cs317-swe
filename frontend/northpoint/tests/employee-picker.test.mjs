import test from 'node:test';
import assert from 'node:assert/strict';
import {bindEmployeePicker} from '../src/employee-picker.js';

function picker(floating=false){
 function node(){return {value:'',hidden:true,style:{},attributes:{},events:{},addEventListener(name,fn){this.events[name]=fn;},removeEventListener(name){delete this.events[name];},setAttribute(name,value){this.attributes[name]=value;},removeAttribute(name){delete this.attributes[name];},setCustomValidity(value){this.validity=value;},scrollIntoView(){this.scrolled=true;}};}
 const input=node(),value=node(),list=node(),status=node(),container=node(),root=node();
 let options=[];
 Object.defineProperty(list,'innerHTML',{get(){return this.html;},set(html){this.html=html;options=[...html.matchAll(/id="(employee-option-\d+)"/g)].map(match=>({...node(),id:match[1]}));}});
 list.querySelectorAll=()=>options;
 input.closest=()=>container;input.getBoundingClientRect=()=>({top:180,bottom:228,left:20,width:320});
 container.contains=target=>target===input;root.querySelector=selector=>({'#record-employee':input,'#record-employee-id':value,'#employee-suggestions':list,'#employee-picker-status':status})[selector];
 if(floating){list.showPopover=()=>list.open=true;list.hidePopover=()=>list.open=false;list.matches=()=>list.open;list.scrollHeight=450;}
 const employees=Array.from({length:8},(_,i)=>({id:'EMP-'+i,name:'Test Employee '+i,department:'Operations'}));
 bindEmployeePicker(root,employees,'',String);
 return {input,value,list,status,root,options:()=>options,fire(name,event={}){input.events[name](event);}};
}
test('suggestions retain keyboard selection and clear the saved ID when typing again',()=>{
 const p=picker();p.fire('focus');assert.equal(p.list.hidden,false);assert.equal(p.options().length,6);assert.equal(p.input.attributes['aria-expanded'],'true');
 p.fire('keydown',{key:'ArrowDown',preventDefault(){}});assert.equal(p.input.attributes['aria-activedescendant'],'employee-option-0');
 p.fire('keydown',{key:'Enter',preventDefault(){}});assert.equal(p.value.value,'EMP-0');assert.equal(p.input.validity,'');assert.equal(p.list.hidden,true);
 p.input.value='New search';p.fire('input');assert.equal(p.value.value,'');assert.ok(p.input.validity);assert.match(p.list.innerHTML,/No matching employees/);assert.equal(p.list.hidden,false);
 p.fire('keydown',{key:'Escape',preventDefault(){},stopPropagation(){}});assert.equal(p.list.hidden,true);assert.equal(p.input.attributes['aria-expanded'],'false');
});
test('a touch selection keeps the input focused and saves an actual employee ID',()=>{
 const p=picker();p.input.value='Employee 3';p.fire('input');let prevented=false;
 const target={closest:()=>({dataset:{employeeOption:'0'}})};
 p.list.events.pointerdown({target,preventDefault(){prevented=true;}});p.list.events.click({target});
 assert.equal(prevented,true);assert.equal(p.value.value,'EMP-3');assert.match(p.status.textContent,/Selected: Test Employee 3/);
});
test('floating suggestions fit the visible viewport and close with the dialog',()=>{
 const oldViewport=globalThis.visualViewport,oldWidth=globalThis.innerWidth,oldHeight=globalThis.innerHeight;
 const events={};globalThis.visualViewport={width:360,height:450,offsetTop:0,offsetLeft:0,addEventListener(name,fn){events[name]=fn;},removeEventListener(name){delete events[name];}};
 try{
  const p=picker(true);p.fire('focus');assert.equal(p.list.open,true);assert.equal(p.list.attributes.popover,'manual');assert.equal(p.list.style.width,'320px');assert.equal(p.list.style.top,'234px');assert.equal(p.list.style.maxHeight,'210px');
  globalThis.visualViewport.height=280;events.resize();assert.equal(p.list.style.top,'6px');assert.equal(p.list.style.maxHeight,'168px');
  p.root.events.close();assert.equal(p.list.open,false);assert.equal(p.list.hidden,true);assert.deepEqual(events,{});
 }finally{globalThis.visualViewport=oldViewport;globalThis.innerWidth=oldWidth;globalThis.innerHeight=oldHeight;}
});
