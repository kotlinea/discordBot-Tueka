import { spawnSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

const output = process.env.BASELINE_OUTPUT || '/tmp/tueka-baseline'
mkdirSync(output, { recursive: true })
const steps = [
  ['typecheck', 'dashboard/frontend', ['run', 'typecheck']],
  ['vitest', 'dashboard/frontend', ['test']],
  ['frontend-build', 'dashboard/frontend', ['run', 'build']],
  ['docs-build', 'docs', ['run', 'build']],
  ['dashboard-playwright', 'dashboard/frontend', ['run', 'test:a11y']],
  ['docs-playwright', 'dashboard/frontend', ['run', 'test:docs-a11y']],
]
const results = []
for (const [name, cwd, args] of steps) {
  const start = performance.now()
  const result = spawnSync('npm', args, { cwd, encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 })
  writeFileSync(join(output, `${name}.log`), `${result.stdout || ''}${result.stderr || ''}${result.error || ''}`)
  const record = { name, command: ['npm', ...args], cwd, exitCode: result.status, signal: result.signal, seconds: +(performance.now() - start).toFixed(0) / 1000 }
  results.push(record)
  console.log(JSON.stringify(record))
  writeFileSync(join(output, 'summary.json'), JSON.stringify({ node: process.version, results }, null, 2))
}
process.exitCode = results.every(result => result.exitCode === 0) ? 0 : 1
