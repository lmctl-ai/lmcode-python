// Low-level compiler-library tooling only; no language block/execution dependency.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));
const {parseDslSchema,compileDsl}=await import(pathToFileURL(process.env.LMCODE_COMPILER_MODULE).href);
const schema=JSON.parse(fs.readFileSync(path.join(here,'../../std/lmcode-std.schema.json')));
schema.name='invocation_vectors';schema.functions.next_counter=[{params:[],returns:'int'}];schema.functions.entry_fail=[{params:[],returns:'void'}];schema.interfaces={Step:{params:[],returns:'int'}};
const raw=JSON.stringify(schema,null,2)+'\n';fs.writeFileSync(path.join(here,'schema.json'),raw);
const parsed=parseDslSchema(Buffer.from(raw),'invocation_vectors',{includeStd:false});
for(const file of fs.readdirSync(here).filter(s=>s.endsWith('.lmcode'))){
 const ownSchema=path.join(here,file.replace(/\.lmcode$/,'.schema.json'));
 const compilerSchema=fs.existsSync(ownSchema)?parseDslSchema(fs.readFileSync(ownSchema),ownSchema):parsed;
 const source=fs.readFileSync(path.join(here,file),'utf8');
 fs.writeFileSync(path.join(here,file.replace(/\.lmcode$/,'.dslb')),compileDsl(source.trimEnd().split('\n'),compilerSchema).bytes);
}
