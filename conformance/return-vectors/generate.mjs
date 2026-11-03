// Fixture-only compiler API. Preserve the original virtual header's line offset.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';
const here=path.dirname(fileURLToPath(import.meta.url));
const {parseDslSchema,compileDsl}=await import(pathToFileURL(process.env.LMCODE_COMPILER_MODULE).href);
const raw=fs.readFileSync(path.join(here,'schema.json'));
const schema=parseDslSchema(raw,'return_vectors',{includeStd:false});
const manifest=JSON.parse(fs.readFileSync(path.join(here,'manifest.json')));
for(const vector of manifest.vectors){
 const source=fs.readFileSync(path.join(here,vector.source),'utf8').trimEnd().split('\n');
 fs.writeFileSync(path.join(here,vector.bytecode),compileDsl(source,schema,(index,column)=>({line:index+2,column})).bytes);
}
execFileSync('python3',[path.join(here,'../../scripts/gen-return-envelopes.py')],{stdio:'inherit'});
