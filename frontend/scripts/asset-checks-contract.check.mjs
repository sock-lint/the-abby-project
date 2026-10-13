import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm, symlink, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { FILES, CHECKS, SCREENSHOTS, KIND, hash, recipe, workbench, bytes, outsideGit, sourceDigest, validateReceipt, contained, png, verifyAssetCopy } from './asset-checks-contract.mjs';

test('recipes allow only bounded declarative woodland operations', () => {
  for (const maxDimension of [128, 256, 384, 512]) assert.equal(recipe({ schemaVersion:1,target:'woodland',operation:'woodland-texture-limit',maxDimension }).maxDimension,maxDimension);
  for (const changed of [{maxDimension:4096},{maxDimension:'256'},{target:'chick'},{operation:'python'},{path:'/tmp/private'},{delivery_review:'public_runtime_accepted'}]) {
    assert.throws(() => recipe({schemaVersion:1,target:'woodland',operation:'woodland-texture-limit',maxDimension:256,...changed}));
  }
});
function receipt() {
  const now = Date.now();
  return {schemaVersion:1,kind:KIND,status:'passed',scope:'private_evaluation',headCommit:'a'.repeat(40),baseCommit:'b'.repeat(40),sourceCommit:'c'.repeat(40),
    issue:1,checkedAt:new Date(now).toISOString(),expiresAt:new Date(now+3600000).toISOString(),catalogSha256:'d'.repeat(64),recipeSha256:'e'.repeat(64),
    sourceManifestSha256:'f'.repeat(64),sourceInputsSha256:'1'.repeat(64),candidateManifestSha256:'2'.repeat(64),
    toolVersions:{node:'22.23.3',blender:'4.1.1',chromium:'146.0.0'},checks:Object.fromEntries(CHECKS.map((key)=>[key,true])),
    screenshots:SCREENSHOTS.map((name)=>({name,path:'/tmp/private/'+name+'.png',sha256:'3'.repeat(64),width:375,height:812})),failureCodes:[]};
}
test('receipts bind exact source/head/digests/checks/screenshot pairs and private scope', () => {
  assert.equal(validateReceipt(receipt()).scope,'private_evaluation');
  for (const mutate of [
    (v)=>{v.scope='public_runtime_accepted';},(v)=>{v.headCommit='main';},(v)=>{v.extra=true;},
    (v)=>{v.checks.animation=false;},(v)=>{delete v.checks.materials;},(v)=>{v.failureCodes.push('FAILED');},
    (v)=>{v.screenshots.pop();},(v)=>{v.screenshots[0].sha256='invalid';},(v)=>{v.screenshots.reverse();},
    (v)=>{v.toolVersions.blender='5.0.0';},
  ]) {const v=receipt();mutate(v);assert.throws(()=>validateReceipt(v));}
});
test('expired, future-dated and overlong receipts are refused', () => {
  for (const [checkedOffset,expireOffset] of [[-7200000,-3600000],[60000,3660000],[0,3600001],[0,-1]]) {
    const now=Date.now(),v=receipt();v.checkedAt=new Date(now+checkedOffset).toISOString();v.expiresAt=new Date(now+expireOffset).toISOString();
    assert.throws(()=>validateReceipt(v));
  }
});
test('fake and oversized PNG evidence is refused', () => {
  const data=Buffer.alloc(24);Buffer.from([137,80,78,71,13,10,26,10]).copy(data);data.write('IHDR',12);data.writeUInt32BE(375,16);data.writeUInt32BE(812,20);
  assert.deepEqual(png(data),{width:375,height:812});data.writeUInt32BE(5000,16);assert.throws(()=>png(data));assert.throws(()=>png(Buffer.from('fake')));
});
test('private readers refuse file links, oversized input and Git output roots', async () => {
  const root=await mkdtemp(join(tmpdir(),'abby-asset-contract-'));
  try {
    const file=join(root,'file');await writeFile(file,'safe');await symlink(file,join(root,'link'));
    await assert.rejects(()=>bytes(join(root,'link')));assert.equal((await bytes(file)).toString(),'safe');await assert.rejects(()=>bytes(file,1));
    await mkdir(join(root,'.git'));await assert.rejects(()=>outsideGit(join(root,'future')));
    assert.equal(contained(root,join(root,'future')),true);assert.equal(contained(root,root),false);assert.equal(contained(root,join(root,'..','other')),false);
  } finally {await rm(root,{recursive:true,force:true});}
});
test('workbench verifies every baseline byte and source manifest against its catalog', async () => {
  const root=await mkdtemp(join(tmpdir(),'abby-asset-catalog-'));
  try {
    const directory=join(root,'baseline');await mkdir(directory);const files={};
    for (const name of FILES.filter((v)=>v!=='manifest.json')) {const data=Buffer.from('synthetic-'+name);await writeFile(join(directory,name),data);files[name]={sha256:hash(data),bytes:data.length};}
    const manifest={schema_version:1,delivery_review:'private_evaluation',models:Object.fromEntries(['chick','bird','woodland'].map((key)=>[key,{file:key+'.glb',sha256:files[key+'.glb'].sha256}]))};
    const data=JSON.stringify(manifest);await writeFile(join(directory,'manifest.json'),data);files['manifest.json']={sha256:hash(data),bytes:Buffer.byteLength(data)};
    const blenderPath=join(root,'blender');await writeFile(blenderPath,'synthetic binary');
    const path=join(root,'workbench.json');await writeFile(path,JSON.stringify({schemaVersion:1,baselineDirectory:directory,files,blenderPath,blenderVersion:'4.1.1'}));
    await verifyAssetCopy(directory, files);
    const selected=await workbench(path);assert.equal(selected.sourceInputsSha256,sourceDigest(files));assert.equal(selected.catalogSha256,hash(await readFile(path)));
    await writeFile(join(directory,'chick.glb'),'changed bytes');await assert.rejects(()=>workbench(path));await assert.rejects(()=>verifyAssetCopy(directory,files));
  } finally {await rm(root,{recursive:true,force:true});}
});
