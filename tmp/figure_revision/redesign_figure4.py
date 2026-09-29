from pathlib import Path
p=Path('scripts/paper_figures.py')
s=p.read_text(encoding='utf-8')
a=s.index('def fig4_blind_timeline():')
b=s.index('\ndef fig5_accrual():',a)
replacement='''def fig4_blind_timeline():
 records=[]
 for i,b in enumerate(BLIND):
  fetch=datetime.fromisoformat(load(latest(b,'planning_comparison')/'planning_comparison.json')['registry_fetched_at'])
  locks=stage_lock_times(b)
  comparisons=[datetime.fromisoformat(load(latest(b,k)/'lock.json')['locked_at'])
   for k in ['planning_comparison','safety_comparison','baseline_comparison','median_comparison','registry_comparison']
   if list((LOCK/b).glob(f'{k}_v*'))]
  freeze=max(locks.values());first=min(comparisons)
  assert freeze<fetch<=first
  records.append((i+1,BLIND[b],freeze,fetch,first,len(locks)))
 f=figure(4.9,'Prediction freeze and blinded evaluation',
  'Every prediction stage was frozen before registry results were retrieved.')
 # The sequence is conceptual; the table below carries the exact measured times.
 a=canvas(f,[.055,.685,.89,.17])
 steps=[('1','Freeze predictions','Record the final model outputs',FITTED),
        ('2','Retrieve results','Access reported trial outcomes',EVIDENCE),
        ('3','Evaluate predictions','Compare forecasts with outcomes',SYNTH)]
 for x,(number,title,body,col) in zip([.005,.35,.695],steps):
  a.add_patch(FancyBboxPatch((x,.07),.30,.86,boxstyle='round,pad=0.004,rounding_size=0.035',fc=PALE[col],ec='none'))
  a.text(x+.022,.69,number,fontsize=9,fontweight='bold',color=col,va='center')
  a.text(x+.061,.69,title,fontsize=8.5,fontweight='bold',color=col,va='center')
  a.text(x+.15,.31,body,fontsize=6.9,ha='center',va='center',color=SLATE)
 for x in [.317,.662]:arrow(a,(x,.50),(x+.027,.50),SLATE)
 f.text(.055,.622,'Recorded study chronology',fontsize=9,fontweight='bold')
 dates={t.date() for r in records for t in r[2:5]}
 assert len(dates)==1
 f.text(.945,.622,next(iter(dates)).strftime('%d %B %Y')+' | UTC',fontsize=7.3,color=SLATE,ha='right')
 a=canvas(f,[.055,.155,.89,.415])
 columns=[.30,.50,.70,.91]
 a.text(.012,.94,'Study',fontsize=7.8,fontweight='bold',va='center')
 for x,txt in zip(columns,['Final prediction\\nfreeze','Results\\nretrieved','First comparison\\nrecorded','Time before\\nretrieval']):
  a.text(x,.94,txt,fontsize=7.7,fontweight='bold',ha='center',va='center',linespacing=1.3,color=SLATE)
 a.plot([0,1],[.805,.805],color='#CCD6DF',lw=.8)
 for row,(number,registry,freeze,fetch,first,count) in enumerate(records):
  y=.67-row*.255
  a.text(.012,y+.029,f'Study {number}',fontsize=9,fontweight='bold',va='center')
  a.text(.012,y-.067,registry,fontsize=7.1,color=SLATE,va='center')
  for x,t,c in zip(columns[:3],[freeze,fetch,first],[FITTED,EVIDENCE,SYNTH]):
   a.text(x,y,t.strftime('%H:%M:%S'),fontsize=9,ha='center',va='center',color=c)
  seconds=int((fetch-freeze).total_seconds());minutes,seconds=divmod(seconds,60)
  elapsed=f'{minutes} min {seconds:02d} s' if minutes else f'{seconds} s'
  a.add_patch(FancyBboxPatch((.812,y-.075),.188,.15,boxstyle='round,pad=0.004,rounding_size=0.025',fc=PALE[FITTED],ec='none'))
  a.text(.906,y,elapsed,fontsize=8.5,fontweight='bold',color=FITTED,ha='center',va='center')
  a.plot([0,1],[y-.145,y-.145],color='#E5EAF0',lw=.6)
 assert all(r[5]==10 for r in records)
 f.text(.055,.088,'All 10 prediction stages preceded retrieval in each study.',fontsize=8,fontweight='bold',color=OBSERVED)
 f.text(.055,.043,'Time before retrieval = registry retrieval time minus the final prediction-freeze time.',fontsize=7.2,color=SLATE)
 save(f,'fig4_blind_timeline')
'''
p.write_text(s[:a]+replacement+s[b:],encoding='utf-8')
p=Path('docs/figures/CAPTIONS.md');s=p.read_text(encoding='utf-8');a=s.index('**Figure 4.');b=s.index('\n\n**Figure 5.',a)
s=s[:a]+'''**Figure 4. Prediction freeze and blinded evaluation.** The sequence shows prediction freeze, registry-result retrieval and subsequent evaluation. The chronology table reports the final prediction-stage freeze, registry retrieval and first comparison-record timestamps for NCT04003610 (Study 1), NCT04205799 (Study 2) and NCT04083170 (Study 3). All times are UTC on 28 September 2026. All ten prediction stages preceded retrieval in each study. The final prediction was frozen 35 seconds, 117 minutes 17 seconds and 84 minutes 56 seconds before retrieval, respectively. The table establishes the recorded order of these operations; timestamps alone do not demonstrate absence of all possible information leakage.'''+s[b:];p.write_text(s,encoding='utf-8')
