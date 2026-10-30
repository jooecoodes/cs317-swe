import test from 'node:test';
import assert from 'node:assert/strict';
import {businessDate,yesterdayComparison,renderYesterdayChange} from '../src/yesterday.js';
const today='2026-10-30';
const employee={id:'EMP-1',apiId:'1',department:'Operations',name:'Test',totalPoints:5,totalStrikes:2};
const record=(id,points=2)=>({id:String(id),employeeId:'EMP-1',employeeApiId:'1',date:'2026-10-30',points,strike:true});
const event=(id,action,targetId,metadata={},date='2026-10-30T01:00:00Z')=>({id:String(id),action,targetId:String(targetId),employeeApiId:'1',metadata,date});
test('yesterday uses the Manila midnight boundary',()=>{assert.equal(businessDate('2026-10-29T15:59:59Z'),'2026-10-29');assert.equal(businessDate('2026-10-29T16:00:00Z'),today);});
test('new employees and issued strikes produce exact net dashboard differences',()=>{
 const result=yesterdayComparison({today,employees:[employee],records:[record(1,2),record(2,3)],events:[event(1,'employee.created',1,{},'2026-10-30T00:00:00Z'),event(2,'violation.assigned',1,{points:2,is_strike:true}),event(3,'violation.assigned',2,{points:3,is_strike:true})]});
 assert.equal(result.employees,1);assert.equal(result.violations,2);assert.equal(result.points,5);assert.equal(result.watchlist,1);assert.equal(result.dailyAverage,2/30);
});
test('removals reconstruct yesterday and crossing the two-strike threshold',()=>{
 const result=yesterdayComparison({today,employees:[{...employee,totalPoints:3,totalStrikes:1}],records:[{...record(1,3),date:'2026-10-28'}],events:[event(4,'violation.removed',2,{points:4,is_strike:true})],removals:[{violationId:'2',originalIssuedAt:'2026-10-28T01:00:00Z'}]});
 assert.equal(result.employees,0);assert.equal(result.violations,-1);assert.equal(result.points,-4);assert.equal(result.watchlist,-1);assert.equal(result.dailyAverage,-1/30);
});
test('legacy hard deletion never fabricates lost points or watchlist totals',()=>{
 const result=yesterdayComparison({today,employees:[],records:[],events:[event(1,'employee.deleted',1,{violation_count:2})]});
 assert.equal(result.employees,-1);assert.equal(result.violations,-2);assert.equal(result.points,null);assert.equal(result.watchlist,null);assert.equal(result.dailyAverage,null);
});
test('new deletion snapshots restore counts, points, watchlist and the previous reporting window',()=>{
 const result=yesterdayComparison({today,employees:[],records:[],events:[event(1,'employee.deleted',1,{violation_count:2,total_points:6,total_strikes:2,violation_records:[{id:1,issued_at:'2026-10-28T01:00:00'},{id:2,issued_at:'2026-10-28T02:00:00'}]})]});
 assert.equal(result.employees,-1);assert.equal(result.violations,-2);assert.equal(result.points,-6);assert.equal(result.watchlist,-1);assert.equal(result.dailyAverage,-2/30);
});
test('department transfers without prior department snapshots do not invent scoped deltas',()=>{const result=yesterdayComparison({today,employees:[employee],records:[],scoped:true,events:[event(1,'employee.updated',1,{changes:{department:'Operations'}})]});assert.equal(result.employees,null);});
test('indicators display signed counts and yesterday labels, never percentages',()=>{const icon=()=>'';assert.match(renderYesterdayChange(3,icon),/\+3/);assert.match(renderYesterdayChange(-2,icon),/-2/);assert.match(renderYesterdayChange(0,icon),/\+0/);assert.match(renderYesterdayChange(null,icon),/vs yesterday/);assert.ok(!renderYesterdayChange(3,icon).includes('%'));assert.ok(!renderYesterdayChange(null,icon,'"<script>').includes('"<script>'));});

test('removal snapshots use the Manila issue date across midnight',()=>{const r=yesterdayComparison({today:'2026-10-30',days:7,employees:[{...employee,totalPoints:0,totalStrikes:0}],records:[],events:[event(4,'violation.removed',2,{points:4,is_strike:true})],removals:[{violationId:'2',originalIssuedAt:'2026-10-29T17:00:00Z'}]});assert.equal(r.dailyAverage,0);});
