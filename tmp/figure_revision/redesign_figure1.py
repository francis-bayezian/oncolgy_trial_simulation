from pathlib import Path
p=Path('scripts/paper_figures.py');s=p.read_text(encoding='utf-8')
s=s.replace("r'\\bV\\d+(?:\\.\\d+)*\\b|", "r'\\b[vV]\\d+(?:\\.\\d+)*\\b|")
s=s.replace("for ext in ('pdf','svg','png'):f.savefig(OUT/f'{name}.{ext}',facecolor='white')", "for ext in ('pdf','svg','png'):\n  metadata={'Creator':'Clinical trial simulation','Producer':'Publication figure generator'} if ext=='pdf' else ({'Creator':'Clinical trial simulation'} if ext=='svg' else {'Software':'Publication figure generator'})\n  f.savefig(OUT/f'{name}.{ext}',facecolor='white',metadata=metadata)")
a=s.index('def fig1_pipeline():');b=s.index('\ndef fig2_evidence_lane():',a)
replacement='''def fig1_pipeline():
 scope=load(ROOT/'data/asset_v1/manifest.json')
 READS.update([ROOT/'data/simulation_parameters_v1/evidence_table.parquet',V3P/'parameter_index.parquet'])
 n=pq.ParquetFile(ROOT/'data/simulation_parameters_v1/evidence_table.parquet').metadata.num_rows
 k=pq.ParquetFile(V3P/'parameter_index.parquet').metadata.num_rows
 assert n==106185 and k==4693
 f=figure(6.6,'From clinical evidence to synthetic trial data',
  'Data quality and statistical conversion establish the foundation for simulation.')
 a=canvas(f,[.055,.075,.89,.80]);xs=[.005,.35,.695];w=.30;h=.175
 def entry(x,y,title,line1,line2,color):
  a.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.004,rounding_size=0.012',fc=PALE[color],ec=color,lw=.75))
  a.text(x+.019,y+.133,title,fontsize=8.5,fontweight='bold',color=color,va='center')
  a.text(x+.019,y+.078,line1,fontsize=7.8,va='center')
  a.text(x+.019,y+.039,line2,fontsize=7.8,va='center')
 a.text(0,.992,'A  Evidence and statistical conversion',fontsize=9,fontweight='bold',color=EVIDENCE)
 a.text(0,.949,'Quality controls: source provenance, denominators and clinical context',fontsize=7.6,color=SLATE)
 evidence=[('Clinical sources',f"{scope['trials']:,} trials",f"{scope['profiles']:,} clinical profiles",EVIDENCE),
  ('Statistical tables',f'{n:,} observations','Counts and denominators',EVIDENCE),
  ('Probability tables',f'{k:,} fitted parameters','Distributions and uncertainty',FITTED)]
 for x,item in zip(xs,evidence):entry(x,.73,*item)
 for i in range(2):arrow(a,(xs[i]+w,.818),(xs[i+1],.818))
 a.text(0,.655,'B  Protocol-informed simulation',fontsize=9,fontweight='bold',color=SLATE)
 simulation=[('Protocol specification','Eligibility and visit schedules','Treatment and endpoint rules',SLATE),
  ('Population and screening','Patient characteristics','Eligibility status and unknowns',SYNTH),
  ('Trial simulation','Enrolment and treatment','Adverse events and endpoints',SYNTH)]
 for x,item in zip(xs,simulation):entry(x,.435,*item)
 for i in range(2):arrow(a,(xs[i]+w,.523),(xs[i+1],.523))
 # Shared probability inputs connect to both population generation and trial simulation.
 a.plot([.845,.845,.50],[.73,.697,.697],color=FITTED,lw=.85)
 arrow(a,(.50,.697),(.50,.61),FITTED)
 arrow(a,(.845,.697),(.845,.61),FITTED)
 # Orthogonal return preserves left-to-right reading in every row.
 a.plot([.98,.98,.155],[.435,.367,.367],color=SYNTH,lw=.85)
 arrow(a,(.155,.367),(.155,.24),SYNTH)
 a.text(.22,.302,'C  Outputs and blinded evaluation',fontsize=9,fontweight='bold',color=SLATE)
 outputs=[('Synthetic records','Participant characteristics','Adverse events and endpoints',SYNTH),
  ('Feasibility estimates','Screening status','Recruitment timelines',SYNTH),
  ('Blinded comparisons','Frozen predictions','Reported registry outcomes',SLATE)]
 for x,item in zip(xs,outputs):entry(x,.065,*item)
 for i in range(2):arrow(a,(xs[i]+w,.153),(xs[i+1],.153))
 f.text(.055,.064,'Recruitment and event-specific safety models use additional registry evidence.',fontsize=7.3,color=SLATE)
 f.text(.055,.033,'Source links, assumptions and unresolved quantities accompany the outputs.',fontsize=7.3,color=SLATE)
 save(f,'fig1_pipeline')
'''
p.write_text(s[:a]+replacement+s[b:],encoding='utf-8')
p=Path('docs/figures/CAPTIONS.md');s=p.read_text(encoding='utf-8');a=s.index('**Figure 1.');b=s.index('\n\n**Figure 2.',a)
s=s[:a]+'''**Figure 1. From clinical evidence to synthetic trial data.** (A) Data-quality controls preserve source provenance, denominators and clinical context as historical clinical sources are converted into statistical observations and fitted probability tables. The evidence foundation contains 1,000 trials, 2,771 clinical profiles, 106,185 observations and 4,693 fitted parameters. (B) Protocol specifications provide eligibility, visit, treatment and endpoint rules; probability tables supply distributions for population generation and trial simulation. Missing eligibility information remains explicit. (C) Simulation produces synthetic records and feasibility estimates, followed by comparison of frozen predictions with retrieved registry outcomes. Every row reads from left to right; the return connector links trial simulation to its outputs. Recruitment and event-specific safety models use additional registry evidence. Source links, assumptions and unresolved quantities accompany the outputs.'''+s[b:];p.write_text(s,encoding='utf-8')
