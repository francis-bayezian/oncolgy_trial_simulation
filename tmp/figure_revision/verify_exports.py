from pathlib import Path
import fitz, re, json
from PIL import Image, ImageOps, ImageDraw
root=Path.cwd()
out=root/'docs/figures'
qa=root/'tmp/figure_revision/pdf_rendered'
qa.mkdir(parents=True,exist_ok=True)
items=[]
for path in sorted(out.glob('fig*.pdf')):
    doc=fitz.open(path)
    assert len(doc)==1
    page=doc[0]
    text=page.get_text()
    assert not re.search(r'\b[vV]\d+(?:\.\d+)*\b|\b[a-f0-9]{16,64}\b|BLIND_|StudySpec|PHASE\d',text),path.name
    png=Image.open(path.with_suffix('.png'))
    assert png.width==4320 and abs(png.info['dpi'][0]-600)<1
    assert all(font[1]!='n/a' for font in page.get_fonts(full=True))
    rendered=qa/(path.stem+'.png')
    page.get_pixmap(dpi=150).save(rendered)
    items.append({'figure':path.stem,'pdf_pages':len(doc),'pdf_size_points':list(page.rect)[2:],'png_pixels':list(png.size),'png_dpi':png.info['dpi'],'pdf_fonts':page.get_fonts(full=True)})
for i in range(0,len(items),2):
    names=[x['figure'] for x in items[i:i+2]]
    ims=[Image.open(qa/(n+'.png')).convert('RGB') for n in names]
    board=Image.new('RGB',(sum(im.width for im in ims)+60,max(im.height for im in ims)+60),'#dfe4e9')
    x=20
    for im in ims:
        board.paste(im,(x,20));x+=im.width+20
    board.save(qa/f'review_{i//2+1}.png')
(qa/'export_checks.json').write_text(json.dumps(items,indent=2))
titles=['Evidence foundation and simulation','Observed counts to probability models','Protocol application and screening','Prediction-freeze timeline','Recruitment and trial outcomes','Calibration and predictive performance','Event-level safety predictions','Aggregate safety and control survival']
md=['# Publication figure gallery','','Eight revised figures with readable scientific labels, consistent typography and spacing, and no visible software versions, hashes or internal parameter codes. Scientific identifiers, qualifiers and uncertainty levels are retained.','','Use **PDF** for scalable publication artwork, **SVG** for vector editing, or **PNG** for 600-dpi insertion. Every figure is 7.2 inches wide; use at full column-spanning width to retain legibility.','','[Publication captions](CAPTIONS.md) | [Source provenance](figure_provenance.json)','','| Figure | Content | Formats |','| --- | --- | --- |']
for i,(it,title) in enumerate(zip(items,titles),1):
    n=it['figure'];md.append(f'| {i} | {title} | [PDF]({n}.pdf) / [SVG]({n}.svg) / [PNG]({n}.png) |')
for i,(it,title) in enumerate(zip(items,titles),1):
    md.extend(['',f'## Figure {i}. {title}','',f'![Figure {i}: {title}]({it["figure"]}.png)'])
(out/'README.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
print(f'Checked and rendered {len(items)} PDFs; confirmed embedded fonts and 600-dpi PNG exports.')
