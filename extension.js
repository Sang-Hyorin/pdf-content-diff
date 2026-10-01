// SPDX-License-Identifier: AGPL-3.0-only
const vscode = require('vscode');
const {spawn} = require('child_process');
const path = require('path');
const {AutoRefresh} = require('./auto_refresh');

exports.activate = context => {
  const log = vscode.window.createOutputChannel('PDF Content Diff');
  context.subscriptions.push(log);
  let watcher, queue = Promise.resolve();
  const serial = task => {
    const result = queue.then(task); queue = result.catch(() => {}); return result;
  };
  function watch(pair) {
    if (watcher) watcher.dispose();
    const config = vscode.workspace.getConfiguration('pdfContentDiff');
    if (!config.get('autoRefresh', true)) return;
    const uris = pair.map(value => vscode.Uri.parse(value));
    if (uris.some(uri => uri.scheme !== 'file')) return;
    watcher = new AutoRefresh(uris.map(uri => uri.fsPath), () => serial(() => show(...uris, true)), {
      delay: config.get('refreshDelay', 1500),
      onError: error => log.appendLine('Automatic refresh: ' + error.message)
    });
  }
  context.subscriptions.push({dispose: () => { if (watcher) watcher.dispose(); }});
  async function show(oldUri, newUri, background = false) {
    try {
      if (oldUri.scheme !== 'file' || newUri.scheme !== 'file') {
        throw new Error('Choose PDFs on the extension host filesystem. In Remote SSH, choose remote files.');
      }
      const output = path.join(path.dirname(newUri.fsPath), path.basename(newUri.fsPath, path.extname(newUri.fsPath))+'_content_comparison.pdf');
      const run = token => new Promise((resolve,reject)=>{
        const configured = vscode.workspace.getConfiguration('pdfContentDiff').get('pythonPath');
        const python = configured || (process.platform==='win32'?'python':'python3');
        const child = spawn(python,[path.join(context.extensionPath,'build_comparison.py'),oldUri.fsPath,newUri.fsPath,output], {windowsHide:true});
        let out='',err='',settled=false;
        child.stdout.setEncoding('utf8');child.stderr.setEncoding('utf8');
        child.stdout.on('data',s=>out+=s);child.stderr.on('data',s=>err+=s);
        const cancel=token.onCancellationRequested(()=>child.kill());
        child.on('error',e=>{settled=true;cancel.dispose();reject(new Error(`Cannot start Python (${python}). Set pdfContentDiff.pythonPath. ${e.message}`));});
        child.on('close',code=>{
          if(settled)return;cancel.dispose();
          if(token.isCancellationRequested)return reject(new vscode.CancellationError());
          if(code!==0)return reject(new Error(err.trim()||'PDF comparison failed. Install PyMuPDF in the configured Python environment.'));
          try{resolve(JSON.parse(out));}catch(e){reject(new Error('Invalid comparison output: '+e.message));}
        });
      });
      const info = background ? await run(vscode.CancellationToken.None) :
        await vscode.window.withProgress({location:vscode.ProgressLocation.Notification,
          title:'Comparing PDF text', cancellable:true},(_,token)=>run(token));
      // Do not send local file paths or document contents to a remote service.
      log.appendLine(`Comparison ${info.cached?'cached':'built'} in ${info.seconds}s; ${info.bytes} bytes.`);
      if (background) return info;
      const pair = [oldUri.toString(),newUri.toString()];
      await context.workspaceState.update('lastPair', pair);
      await context.globalState.update('lastPair', pair);
      watch(pair);
      const uri=vscode.Uri.file(info.output);
      if(vscode.extensions.getExtension('mathematic.vscode-pdf')) {
        await vscode.commands.executeCommand('vscode.openWith',uri,'pdf.view',{preview:false});
      }else{
        await vscode.commands.executeCommand('vscode.open',uri,{preview:false});
        vscode.window.showInformationMessage('Install a PDF viewer extension to preview the comparison inside VS Code.');
      }
    }catch(e){
      if (background) throw e;
      if(!(e instanceof vscode.CancellationError))vscode.window.showErrorMessage('PDF Content Diff: '+e.message);
    }
  }
  const choose=async()=>{
    const pick=async title=>(await vscode.window.showOpenDialog({title,canSelectMany:false,filters:{PDF:['pdf']}}))?.[0];
    const old=await pick('Choose the older PDF');if(!old)return;
    const revised=await pick('Choose the newer PDF');if(revised)return serial(() => show(old,revised));
  };
  const last=async()=>{
    const pair=context.workspaceState.get('lastPair') || vscode.workspace.getConfiguration('pdfContentDiff').get('watchPair') || context.globalState.get('lastPair');
    if(!pair || pair.length !== 2)return choose();
    return serial(() => show(...pair.map(value=>vscode.Uri.parse(value))));
  };
  context.subscriptions.push(vscode.commands.registerCommand('pdfContentDiff.compare',choose),
    vscode.commands.registerCommand('pdfContentDiff.compareLast',last));
  const restore = () => {
    const pair = context.workspaceState.get('lastPair') || vscode.workspace.getConfiguration('pdfContentDiff').get('watchPair');
    if (pair && pair.length === 2) watch(pair);
    else if (watcher) watcher.dispose();
  };
  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration(e => {
    if (e.affectsConfiguration('pdfContentDiff')) restore();
  }));
  restore();
};
