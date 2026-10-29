import { compile, compileAST, parse } from '../../packages/srg-compiler/dist/index.js';

let input = '';
let request;
process.stdin.setEncoding('utf8');
for await (const chunk of process.stdin) {
  input += chunk;
}

try {
  request = JSON.parse(input);
  const { source, locations, ast, compile_ast } = request;
  const value = compile_ast
    ? compileAST(compile_ast)
    : ast
    ? await parse(source)
    : locations
    ? (await parse(source)).definitions.map(definition => definition.loc)
    : await compile(source);
  process.stdout.write(JSON.stringify({ ok: true, value }));
} catch (error) {
  const loc = error.loc;
  const failure = {
    ok: false,
    name: error.name,
    line: loc?.start?.line ?? null,
    column: loc?.start?.column ?? null,
  };
  if (request?.message) {
    failure.message = error.message;
  }
  process.stdout.write(JSON.stringify(failure));
}
