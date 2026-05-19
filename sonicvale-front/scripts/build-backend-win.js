const fs = require('fs')
const path = require('path')
const { spawnSync } = require('child_process')

if (process.platform !== 'win32') {
  console.error('build-backend-win 仅支持在 Windows 上运行。')
  process.exit(1)
}

const frontRoot = path.resolve(__dirname, '..')
const repoRoot = path.resolve(frontRoot, '..')
const backendRoot = path.join(repoRoot, 'SonicVale')
const entryFile = path.join(backendRoot, 'run.py')
const outputDir = path.join(frontRoot, 'electron')
const buildRoot = path.join(frontRoot, '.build', 'pyinstaller')
const exePath = path.join(outputDir, 'main.exe')

if (!fs.existsSync(entryFile)) {
  console.error(`未找到后端打包入口: ${entryFile}`)
  process.exit(1)
}

fs.mkdirSync(buildRoot, { recursive: true })

const venvPython = path.join(backendRoot, 'venv', 'Scripts', 'python.exe')
const pythonCandidates = [
  {
    command: venvPython,
    args: []
  },
  {
    command: 'py',
    args: ['-3']
  },
  {
    command: 'python',
    args: []
  }
]

function runCommand(command, args, options = {}) {
  return spawnSync(command, args, {
    cwd: backendRoot,
    shell: false,
    ...options
  })
}

function commandLabel(candidate) {
  return [candidate.command, ...candidate.args].join(' ')
}

function validatePython(candidate) {
  const result = runCommand(
    candidate.command,
    [
      ...candidate.args,
      '-c',
      [
        'import importlib.util',
        'mods = ["uvicorn", "fastapi", "openpyxl", "numpy"]',
        'missing = [m for m in mods if importlib.util.find_spec(m) is None]',
        'raise SystemExit(0 if not missing else 3)'
      ].join('; ')
    ],
    { stdio: 'pipe', encoding: 'utf8' }
  )

  return result.status === 0
}

function choosePythonCandidate() {
  for (const candidate of pythonCandidates) {
    if (path.isAbsolute(candidate.command) && !fs.existsSync(candidate.command)) {
      continue
    }

    const versionCheck = runCommand(candidate.command, [...candidate.args, '--version'], {
      stdio: 'pipe',
      encoding: 'utf8'
    })

    if (versionCheck.error || versionCheck.status !== 0) {
      continue
    }

    if (validatePython(candidate)) {
      return candidate
    }
  }

  return null
}

const pythonCandidate = choosePythonCandidate()

if (!pythonCandidate) {
  console.error('未找到可用于后端打包的 Python 环境。')
  console.error('请确认以下两点之一成立：')
  console.error('1. SonicVale/venv 可正常使用且已安装 requirements.txt')
  console.error('2. 系统 Python 已安装 requirements.txt 和 pyinstaller')
  console.error('可执行：py -3 -m pip install -r SonicVale\\requirements.txt')
  console.error('再执行：py -3 -m pip install pyinstaller')
  process.exit(1)
}

const pyInstallerArgs = [
  ...pythonCandidate.args,
  '-m',
  'PyInstaller',
  '--noconfirm',
  '--clean',
  '--onefile',
  '--name',
  'main',
  '--distpath',
  outputDir,
  '--workpath',
  path.join(buildRoot, 'work'),
  '--specpath',
  buildRoot,
  entryFile
]

const result = runCommand(pythonCandidate.command, pyInstallerArgs, { stdio: 'inherit' })

if (result.error || result.status !== 0) {
  console.error(`后端 main.exe 打包失败，使用的 Python: ${commandLabel(pythonCandidate)}`)
  if (result.error) {
    console.error(result.error.message)
  } else {
    console.error(`退出码: ${result.status}`)
  }
  process.exit(1)
}

if (!fs.existsSync(exePath)) {
  console.error(`PyInstaller 已执行，但未生成预期文件: ${exePath}`)
  process.exit(1)
}

console.log(`后端已打包完成: ${exePath}`)
console.log(`使用的 Python: ${commandLabel(pythonCandidate)}`)
