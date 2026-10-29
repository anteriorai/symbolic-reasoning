/**
 * WASM loader for SRG parser
 * Handles initialization across different environments (Node.js, browser)
 */

import { Parser, Language } from 'web-tree-sitter';

// Global parser state
let parserInstance: Parser | null = null;
let languageInstance: Language | null = null;
let initializationPromise: Promise<void> | null = null;

/**
 * Resolve WASM file path/URL
 */
async function resolveWasmUrl(
  filename: 'tree-sitter.wasm' | 'tree-sitter-srg.wasm'
): Promise<string> {
  const url =
    filename === 'tree-sitter.wasm'
      ? new URL('../wasm/tree-sitter.wasm', import.meta.url)
      : new URL('../wasm/tree-sitter-srg.wasm', import.meta.url);

  // In Node.js, web-tree-sitter accepts a filesystem path
  if (typeof process !== 'undefined' && process.versions && process.versions.node) {
    // Dynamic import to avoid breaking browser builds that don't shim 'url'
    const { fileURLToPath } = await import('node:url');
    return fileURLToPath(url);
  }

  // In the browser, bundlers rewrite this to the final asset URL
  return url.href;
}

/**
 * Options for providing pre-loaded WASM binaries, bypassing import.meta.url
 * resolution. Useful when WASM files are embedded in a compiled binary
 * (e.g. via Bun's `with { type: "file" }` imports).
 *
 * Accepts either raw bytes (ArrayBuffer/Uint8Array) or a filesystem path.
 */
export interface InitParserOptions {
  treeSitterWasm?: string | ArrayBuffer | Uint8Array;
  srgWasm?: string | Uint8Array;
}

/**
 * Initialize the parser
 * Safe to call multiple times - subsequent calls return the same promise
 */
export async function initParser(options?: InitParserOptions): Promise<void> {
  if (initializationPromise) return initializationPromise;

  initializationPromise = (async () => {
    try {
      const treeSitterOpt = options?.treeSitterWasm;
      if (treeSitterOpt && typeof treeSitterOpt !== 'string') {
        // Pre-loaded binary — pass directly to Emscripten, skip file resolution.
        // Pass Uint8Array as-is so Emscripten honors byteOffset/byteLength
        // (using `.buffer` would expose bytes outside the view's window).
        await Parser.init({ wasmBinary: treeSitterOpt } as any);
      } else {
        const treeSitterPath = treeSitterOpt
          ?? await resolveWasmUrl('tree-sitter.wasm');
        await Parser.init({
          locateFile: () => treeSitterPath,
        });
      }

      const parser = new Parser();
      const srgOpt = options?.srgWasm;
      const lang = await Language.load(
        srgOpt ?? await resolveWasmUrl('tree-sitter-srg.wasm')
      );
      
      parser.setLanguage(lang);
      
      parserInstance = parser;
      languageInstance = lang;
    } catch (err) {
      // Reset on failure so retry is possible
      parserInstance = null;
      languageInstance = null;
      initializationPromise = null;
      throw new Error(`Failed to initialize SRG parser: ${err}`);
    }
  })();

  return initializationPromise;
}

/**
 * Check if parser is initialized
 */
export function isParserInitialized(): boolean {
  return parserInstance !== null && languageInstance !== null;
}

/**
 * Get the parser instance
 * Throws if parser is not initialized
 */
export function getParser(): Parser {
  if (!parserInstance) {
    throw new Error('Parser not initialized. Call initParser() first.');
  }
  return parserInstance;
}

/**
 * Get the language instance
 * Throws if parser is not initialized
 */
export function getLanguage(): Language {
  if (!languageInstance) {
    throw new Error('Parser not initialized. Call initParser() first.');
  }
  return languageInstance;
}

/**
 * Reset parser state (useful for testing)
 * @internal
 */
export function resetParser(): void {
  parserInstance = null;
  languageInstance = null;
  initializationPromise = null;
}
