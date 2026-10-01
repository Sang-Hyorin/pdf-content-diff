"""Build a dependency-free VSIX archive containing first-party source only."""
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parents[1]
meta = json.loads((root/'package.json').read_text(encoding='utf-8'))
target = Path(sys.argv[1] if len(sys.argv)>1 else 'dist/pdf-content-diff.vsix')
target.parent.mkdir(parents=True, exist_ok=True)
manifest = f'''<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
<Metadata><Identity Language="en-US" Id="{meta['name']}" Version="{meta['version']}" Publisher="{meta['publisher']}"/><DisplayName>{escape(meta['displayName'])}</DisplayName><Description xml:space="preserve">{escape(meta['description'])}</Description><Tags>pdf,diff,review</Tags><Categories>Visualization</Categories><GalleryFlags>Public</GalleryFlags><Properties><Property Id="Microsoft.VisualStudio.Code.Engine" Value="{meta['engines']['vscode']}"/><Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace"/></Properties></Metadata>
<Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation><Dependencies/><Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/><Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true"/><Asset Type="Microsoft.VisualStudio.Services.Content.License" Path="extension/LICENSE" Addressable="true"/></Assets></PackageManifest>'''
content = '''<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="json" ContentType="application/json"/><Default Extension="js" ContentType="application/javascript"/><Default Extension="py" ContentType="text/plain"/><Default Extension="md" ContentType="text/markdown"/><Default Extension="txt" ContentType="text/plain"/><Default Extension="png" ContentType="image/png"/><Default Extension="vsixmanifest" ContentType="text/xml"/></Types>'''
with ZipFile(target, 'w', ZIP_DEFLATED) as z:
    z.writestr('extension.vsixmanifest', manifest)
    z.writestr('[Content_Types].xml', content)
    for name in ['package.json','extension.js','auto_refresh.js','backend.py','build_comparison.py','README.md','README.zh-CN.md','CHANGELOG.md','LICENSE','requirements.txt','docs/preview.png']:
        z.write(root/name,'extension/'+name)
print(target)
