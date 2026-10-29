#!/usr/bin/env node
/**
 * Copy WASM files needed for the parser
 * - tree-sitter.wasm and its LICENSE from web-tree-sitter
 * - tree-sitter-srg.wasm from @anteriorai/srg-grammar
 */

import { copyFile, mkdir, access } from 'fs/promises';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = join(__dirname, '..');

async function fileExists(path) {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

async function copyWasmFiles() {
  console.log('📦 Copying WASM files...');
  
  const wasmDir = join(projectRoot, 'wasm');
  
  // Ensure wasm directory exists
  await mkdir(wasmDir, { recursive: true });
  
  try {
    // Copy tree-sitter.wasm from web-tree-sitter
    // Try package node_modules first, then workspace root
    const treeSitterPaths = [
      join(projectRoot, 'node_modules', 'web-tree-sitter', 'tree-sitter.wasm'),
      join(projectRoot, '..', '..', 'node_modules', 'web-tree-sitter', 'tree-sitter.wasm'),
    ];
    
    let treeSitterCopied = false;
    for (const treeSitterWasm of treeSitterPaths) {
      if (await fileExists(treeSitterWasm)) {
        await copyFile(treeSitterWasm, join(wasmDir, 'tree-sitter.wasm'));
        await copyFile(join(dirname(treeSitterWasm), 'LICENSE'), join(wasmDir, 'LICENSE.tree-sitter'));
        console.log('  ✓ tree-sitter.wasm');
        treeSitterCopied = true;
        break;
      }
    }
    
    if (!treeSitterCopied) {
      console.warn('  ⚠ tree-sitter.wasm not found, skipping');
    }
    
    // Copy tree-sitter-srg.wasm from @anteriorai/srg-grammar
    // Try both workspace location and node_modules
    const srgWasmPaths = [
      join(projectRoot, '..', 'srg-grammar', 'tree-sitter-srg.wasm'),
      join(projectRoot, 'node_modules', '@anteriorai', 'srg-grammar', 'tree-sitter-srg.wasm'),
    ];
    
    let srgWasmCopied = false;
    for (const srgWasm of srgWasmPaths) {
      if (await fileExists(srgWasm)) {
        await copyFile(srgWasm, join(wasmDir, 'tree-sitter-srg.wasm'));
        console.log('  ✓ tree-sitter-srg.wasm');
        srgWasmCopied = true;
        break;
      }
    }
    
    if (!srgWasmCopied) {
      console.warn('  ⚠ tree-sitter-srg.wasm not found, skipping');
      console.warn('    Please build @anteriorai/srg-grammar first: npm run generate -w @anteriorai/srg-grammar');
    }
    
    console.log('✅ WASM files copied successfully');
  } catch (error) {
    console.error('❌ Failed to copy WASM files:', error.message);
    // Don't fail the build if WASM files aren't available yet
    // They might be copied later or already exist
    process.exit(0);
  }
}

copyWasmFiles().catch(error => {
  console.error('❌ Error:', error);
  process.exit(0); // Don't fail the build
});

