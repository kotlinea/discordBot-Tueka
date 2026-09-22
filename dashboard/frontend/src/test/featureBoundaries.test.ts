import { posix } from 'node:path'
import ts from 'typescript'
import { describe, expect, it } from 'vitest'

function targets(file: string, source: string) {
  const result: string[] = []
  const tree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  function visit(node: ts.Node) {
    let specifier: ts.Node | undefined
    if (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) specifier = node.moduleSpecifier
    if (ts.isImportTypeNode(node) && ts.isLiteralTypeNode(node.argument)) specifier = node.argument.literal
    if (ts.isCallExpression(node) && (node.expression.kind === ts.SyntaxKind.ImportKeyword || node.expression.getText(tree) === 'require')) specifier = node.arguments[0]
    if (specifier && ts.isStringLiteralLike(specifier)) result.push(specifier.text)
    ts.forEachChild(node, visit)
  }
  visit(tree)
  return result
}

function violations(sources: Record<string, string>) {
  const edges = new Map<string, string[]>()
  const category = (file: string) => /^features\/([^/]+)\//.exec(file)?.[1]
  for (const [file, source] of Object.entries(sources)) {
    edges.set(file, targets(file, source).filter(target => target.startsWith('.')).map(target => {
      const base = posix.normalize(posix.join(posix.dirname(file), target))
      return [base, base + '.ts', base + '.tsx', base + '/index.ts', base + '/index.tsx'].find(value => value in sources) ?? base
    }))
  }
  const errors: string[] = []
  for (const file of edges.keys()) {
    const seen = new Set<string>()
    const inspect = (target: string, chain: string[]) => {
      if (seen.has(target)) return
      seen.add(target)
      const path = [...chain, target]
      if ((file.startsWith('components/') && /^(features|app|routing)\//.test(target)) ||
          (category(file) && category(target) && category(file) !== category(target))) {
        errors.push(path.join(' -> '))
        return
      }
      for (const next of edges.get(target) ?? []) inspect(next, path)
    }
    for (const target of edges.get(file) ?? []) inspect(target, [file])
  }
  return errors
}

describe('UI dependency boundaries', () => {
  it('keeps shared UI independent of features and category implementations independent of each other', () => {
    const files = import.meta.glob('../**/*.{ts,tsx}', { query: '?raw', import: 'default', eager: true }) as Record<string, string>
    const sources = Object.fromEntries(Object.entries(files).filter(([file]) => !file.startsWith('../test/')).map(([file, value]) => [file.slice(3), value]))
    expect(violations(sources)).toEqual([])
  })
  it.each([
    "import type { Model } from '../features/community/model'",
    "export { Screen } from '../features/community/model'",
    "const load = () => import('../features/community/model')",
    "type Model = import('../features/community/model').Model",
    "const model = require('../features/community/model')",
  ])('rejects shared UI reverse dependency: %s', source => {
    expect(violations({ 'components/Shared.tsx': source })).not.toEqual([])
  })
  it('follows barrel exports and helper indirection across categories', () => {
    expect(violations({
      'components/Shared.tsx': "import { Screen } from '../helper'",
      'helper.ts': "export { Screen } from './features/community/screen'",
      'features/community/screen.tsx': "import { rules } from '../moderation/rules'",
      'features/moderation/rules.ts': 'export const rules = []',
    })).toEqual(expect.arrayContaining([
      'components/Shared.tsx -> helper.ts -> features/community/screen.tsx',
      'features/community/screen.tsx -> features/moderation/rules.ts',
    ]))
  })
  it('allows owned screens and shared components', () => {
    expect(violations({
      'features/example/probe.feature.tsx': "export { Screen } from './screen'",
      'features/example/screen.tsx': "import { Button } from '../../components/Button'",
      'components/Button.tsx': 'export const Button = () => null',
    })).toEqual([])
  })
})
