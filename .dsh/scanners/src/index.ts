/**
 * mygui-scanners — public surface of the MyGUI DSH Scanner infrastructure.
 *
 * Exports the scanner contracts, the `myguiScanners` registry service and
 * plugin, the architecture scanner and its plugin entry, and the rule
 * implementations. Nothing here is model-facing.
 */

export * from './contracts.ts';

export {
  MyguiScannersService,
  validateScannerResult,
  type ScannerDescriptor,
} from './registry/service.ts';
export { default as myguiScannerRegistryPlugin, name as myguiScannerRegistryName, provide as myguiScannerRegistryProvide } from './registry/plugin.ts';

export { createArchitectureScanner } from './scanners/architecture/scanner.ts';
export {
  default as myguiScannerArchitecturePlugin,
  name as myguiScannerArchitectureName,
} from './scanners/architecture/plugin.ts';
export {
  ARCHITECTURE_RULES,
  type ArchitectureRule,
  type RuleOutcome,
  type RuleRunContext,
} from './scanners/architecture/rules/index.ts';
export { DEFAULT_EXCLUDE } from './scanners/architecture/scanner.ts';
