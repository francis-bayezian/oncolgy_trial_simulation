"""Publication figures from existing evidence. Run with .venv-figures/Scripts/python.exe.

Scientific inputs remain in the released/locked artifacts. Internal identifiers and
versions are recorded in figure_provenance.json, never used as display labels.
"""
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pyarrow.parquet as pq
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/figures'
LOCK = ROOT / 'data/locked'
V3P = ROOT / 'data/simulation_parameters_v3/proportions'
EVIDENCE, FITTED, SYNTH = '#23649A', '#7051A3', '#187F80'
OBSERVED, UNKNOWN, PROTOCOL = '#242D37', '#89949D', '#C45E20'
SLATE = '#40566C'
PALE = {EVIDENCE:'#EDF4FA', FITTED:'#F2EEF8', SYNTH:'#EDF7F5', SLATE:'#F0F3F6', UNKNOWN:'#F3F4F5'}
WIDTH = 7.2
BLIND = {'BLIND_1':'NCT04003610','BLIND_2':'NCT04205799','BLIND_3':'NCT04083170'}
READS, AUDIT = set(), []
mpl.rcParams.update({
 'font.family':'sans-serif', 'font.sans-serif':['Arial','DejaVu Sans'],
 'font.size':8, 'axes.labelsize':8, 'axes.titlesize':9, 'axes.titleweight':'bold',
 'xtick.labelsize':7.5, 'ytick.labelsize':8, 'legend.fontsize':7.3,
 'text.color':OBSERVED, 'axes.labelcolor':OBSERVED, 'xtick.color':SLATE, 'ytick.color':OBSERVED,
 'axes.spines.top':False, 'axes.spines.right':False, 'axes.linewidth':0.65,
 'xtick.major.width':0.6, 'ytick.major.width':0.6, 'xtick.major.size':3,
 'pdf.fonttype':42, 'ps.fonttype':42, 'svg.fonttype':'none', 'savefig.dpi':600,
 'legend.frameon':False, 'axes.titlelocation':'left', 'axes.axisbelow':True,
 'figure.facecolor':'white', 'axes.facecolor':'white', 'axes.unicode_minus':False,
})

def load(path):
 path=Path(path); READS.add(path); return json.loads(path.read_text(encoding='utf-8'))

def latest(study,kind):
 candidates=[p for p in (LOCK/study).glob(f'{kind}_v*') if re.fullmatch(rf'{kind}_v[\d.]+',p.name)]
 return max(candidates,key=lambda p:tuple(map(int,p.name.rsplit('_v',1)[1].split('.'))))

def figure(height,title,subtitle):
 f=plt.figure(figsize=(WIDTH,height))
 f.text(.055,.974,title,fontsize=12,fontweight='bold',va='top')
 f.text(.055,.974-.28/height,subtitle,fontsize=8,color=SLATE,va='top')
 return f

def heading(f,x,y,letter,title):
 f.text(x,y,f'{letter}  {title}',fontsize=9,fontweight='bold',va='bottom')

def percent(ax):
 ax.set_xlim(0,1); ax.set_xticks([0,.25,.5,.75,1]); ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1,decimals=0))
 ax.grid(axis='x',color='#E5EAF0',lw=.5); ax.tick_params(axis='y',length=0)
 ax.spines['left'].set_visible(False)

def card(ax,x,y,w,h,title,body,color):
 patch=FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.004,rounding_size=0.012',fc=PALE[color],ec=color,lw=.8)
 ax.add_patch(patch)
 ax.text(x+w/2,y+h*.83,title,fontsize=8.5,fontweight='bold',color=color,ha='center',va='top',linespacing=1.15)
 ax.text(x+w/2,y+h*.16,body,fontsize=7.7,ha='center',va='bottom',linespacing=1.35)

def arrow(ax,p,q,color=SLATE,rad=0):
 ax.add_patch(FancyArrowPatch(p,q,arrowstyle='-|>',mutation_scale=9,color=color,lw=.85,
  connectionstyle=f'arc3,rad={rad}',shrinkA=3,shrinkB=3))

def canvas(f,bounds):
 ax=f.add_axes(bounds);ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off');return ax

def save(f,name):
 f.canvas.draw(); renderer=f.canvas.get_renderer(); texts=[]; outside=[]
 for t in f.findobj(mpl.text.Text):
  if not t.get_visible() or not t.get_text():continue
  value=t.get_text();texts.append(value)
  if re.search(r'\b[vV]\d+(?:\.\d+)*\b|\b[a-f0-9]{16,64}\b|BLIND_|StudySpec|PHASE\d',value):
   raise ValueError(f'Internal display label in {name}: {value}')
  # Only visible axis tick labels are included by get_visible(). Allow a 2-pixel antialias margin.
  bb=t.get_window_extent(renderer)
  if bb.width and bb.height and (bb.x0 < -2 or bb.y0 < -2 or bb.x1>f.bbox.width+2 or bb.y1>f.bbox.height+2):outside.append(value)
 if outside:raise ValueError(f'Text outside figure canvas in {name}: {outside}')
 OUT.mkdir(parents=True,exist_ok=True)
 for ext in ('pdf','svg','png'):
  metadata={'Creator':'Clinical trial simulation','Producer':'Publication figure generator'} if ext=='pdf' else ({'Creator':'Clinical trial simulation'} if ext=='svg' else {'Software':'Publication figure generator'})
  f.savefig(OUT/f'{name}.{ext}',facecolor='white',metadata=metadata)
 AUDIT.append({'figure':name,'size_inches':list(f.get_size_inches()),'png_dpi':600,'visible_text':texts})
 plt.close(f);print('Wrote',name,flush=True)

def fig1_pipeline():
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
 a.plot([.98,.98,-.04,-.04],[.435,.367,.367,.153],color=SYNTH,lw=.85,clip_on=False)
 connector=FancyArrowPatch((-.04,.153),(.005,.153),arrowstyle='-|>',mutation_scale=9,color=SYNTH,lw=.85,shrinkA=0,shrinkB=3,clip_on=False)
 a.add_patch(connector)
 a.text(0,.302,'C  Outputs and blinded evaluation',fontsize=9,fontweight='bold',color=SLATE)
 outputs=[('Synthetic records','Participant characteristics','Adverse events and endpoints',SYNTH),
  ('Feasibility estimates','Screening status','Recruitment timelines',SYNTH),
  ('Blinded comparisons','Frozen predictions','Reported registry outcomes',SLATE)]
 for x,item in zip(xs,outputs):entry(x,.065,*item)
 for i in range(2):arrow(a,(xs[i]+w,.153),(xs[i+1],.153))
 f.text(.055,.064,'Recruitment and event-specific safety models use additional registry evidence.',fontsize=7.3,color=SLATE)
 f.text(.055,.033,'Source links, assumptions and unresolved quantities accompany the outputs.',fontsize=7.3,color=SLATE)
 save(f,'fig1_pipeline')

def fig2_evidence_lane():
 pid,oid='3b1473de78a0a559','d9b934b17937e424'
 raw=load(ROOT/'data/raw/ctgov/NCT00091572.json')
 g=next(e for e in raw['resultsSection']['adverseEventsModule']['eventGroups'] if e['id']=='EG000')
 assert (g['seriousNumAffected'],g['seriousNumAtRisk'])==(124,419)
 rec=next(json.loads(l) for l in (V3P/'parameter_index.jsonl').read_text(encoding='utf-8').splitlines() if pid in l)
 READS.add(V3P/'parameter_index.jsonl');READS.add(V3P/'posterior_draws.parquet')
 d=pq.read_table(V3P/'posterior_draws.parquet',filters=[('parameter_id','=',pid)])
 pop=np.asarray(d['population'].to_pylist());fut=np.asarray(d['future_study'].to_pylist())
 f=figure(7.6,'From an observed count to a probability model','Temozolomide in melanoma | NCT00091572 | Any serious adverse event')
 heading(f,.055,.885,'A','Preserving the statistical meaning')
 a=canvas(f,[.055,.71,.89,.155])
 for x,t,b,c in [(0.005,'Reported count','124 affected\n419 participants at risk',EVIDENCE),(.35,'Statistical observation','Serious events, any cause\nSafety denominator retained',EVIDENCE),(.695,'Fitted probability model','1 directly supporting study\n6 studies supporting borrowing',FITTED)]:card(a,x,.03,.30,.94,t,b,c)
 arrow(a,(.307,.5),(.345,.5));arrow(a,(.652,.5),(.690,.5))
 heading(f,.055,.665,'B','Three distributions answer different questions')
 ax=f.add_axes([.43,.365,.51,.28]);x=np.linspace(.001,.999,1000)
 def kde(v):
  z=np.log(v/(1-v));k=stats.gaussian_kde(z);k.set_bandwidth(k.factor*1.25)
  return k(np.log(x/(1-x)))/(x*(1-x))
 rr=[('Within-study posterior','This study alone',stats.beta.pdf(x,124.5,295.5),rec['within_study_posterior'],EVIDENCE),
 ('Population posterior','Historical evidence with borrowing',kde(pop),rec['population_posterior'],FITTED),
 ('Future-study probability','Probability in a new study',kde(fut),rec['future_study_predictive'],SYNTH)]
 for i,(name,note,density,q,c) in enumerate(rr):
  y=2-i;h=.62*density/density.max()
  ax.fill_between(x,y,y+h,color=c,alpha=.18,lw=0);ax.plot(x,y+h,color=c,lw=1.05)
  ax.plot([q['q025'],q['q975']],[y-.10]*2,color=c,lw=2);ax.plot(q['median'],y-.10,'o',color=c,ms=4,mec='white',mew=.5)
  fy=.365+.28*((y+.33+.27)/3.12)
  f.text(.065,fy,name,color=c,fontsize=8.3,fontweight='bold',va='center')
  f.text(.065,fy-.022,note,fontsize=7.3,color=SLATE,va='center')
  f.text(.065,fy-.043,f"Median {q['median']:.1%}; 95% interval {q['q025']:.1%}-{q['q975']:.1%}",fontsize=7.1,va='center')
 ax.axvline(124/419,color=OBSERVED,ls=(0,(3,3)),lw=.8)
 ax.set_ylim(-.27,2.85);ax.set_yticks([]);percent(ax);ax.set_xlabel('Probability of any serious adverse event')
 ax.text(.99,1.01,'Dashed line: observed 124/419',transform=ax.transAxes,ha='right',fontsize=7,color=SLATE)
 heading(f,.055,.278,'C','Contribution of broader evidence')
 ax=f.add_axes([.43,.095,.51,.16]);chain=rec['parent_contribution']['chain']
 for i,item in enumerate(chain):
  y=3-i;v=item['share_of_precision_from_parent'];ax.barh(y,1,color='#EDF1F5',height=.52);ax.barh(y,v,color=FITTED,height=.52)
  ax.text(v+.015,y,f'{v:.0%}',va='center',fontsize=7.5)
 labels=['Cytotoxic chemotherapy (162 studies)','Alkylating agents (13 studies)','Temozolomide (7 studies)','Melanoma and skin cancer (1 study)']
 ax.set_yticks(range(4),labels=labels[::-1],fontsize=7.3);percent(ax)
 ax.set_xlabel('Posterior precision supplied by broader evidence',fontsize=7.5)
 f.text(.055,.032,'Borrowing percentages describe model precision, not the proportion of patients borrowed.',fontsize=7.2,color=SLATE)
 save(f,'fig2_evidence_lane')

def fig3_walkthrough():
 b='ACNS0332';el=load(latest(b,'eligibility')/'eligibility_summary.json')['summary']
 rec=load(latest(b,'cohorts')/'recruitment_summary.json');om=load(latest(b,'outcomes')/'outcome_model.json')['control_efs']
 cmp=load(latest(b,'registry_comparison')/'comparison.json');ctl=next(i for i in cmp['items'] if i['quantity'].startswith('5-year EFS %') and 'control' in i['quantity'])
 f=figure(6.8,'Applying a protocol to a synthetic cohort','ACNS0332 | Development example; outcomes were known during model development')
 heading(f,.055,.88,'A','Screening rules and missing patient information')
 ax=f.add_axes([.42,.565,.52,.285]);c=el['criteria'];per=el['per_criterion']
 met=sum(per[v]['met']==el['patients'] for v in c['evaluated']);unk=sum(per[v]['unknown']==el['patients'] for v in c['evaluated'])
 cats=[('Evaluable for every patient',met,SYNTH),('Patient variable unavailable',unk,UNKNOWN),('Rule unresolved',len(c['not_executable']),PROTOCOL),('Procedural requirements',len(c['procedural']),SLATE),('Optional or informational',len(c['permissive'])+len(c['informational']),'#BAC3CB')]
 for i,(label,n,col) in enumerate(cats):
  y=4-i;ax.barh(y,n,color=col,height=.52);ax.text(n+.35,y,str(n),va='center')
 ax.set_yticks(range(5),[x[0] for x in cats][::-1]);ax.tick_params(axis='y',length=0);ax.spines['left'].set_visible(False)
 ax.set_xlim(0,23);ax.set_xlabel(f'Number of criteria (total {sum(x[1] for x in cats)})');ax.set_xticks([0,5,10,15,20])
 sc=el['status_counts'];f.text(.055,.505,f"{el['patients']:,} screened: {sc['ELIGIBLE']:,} confirmed eligible; {sc['UNDETERMINED']:,} undetermined; {sc['INELIGIBLE']:,} ineligible.",fontsize=8)
 heading(f,.055,.455,'B','Enrolment scenarios');heading(f,.565,.455,'C','Control-arm event-free survival')
 ax=f.add_axes([.12,.13,.34,.285]);target=rec['summary']['target']['patients']
 for rate,ls in [(35,'-'),(60,'--')]:
  p=latest(b,'cohorts')/f'cohort_accrual_{rate}_per_year.jsonl';READS.add(p)
  years=np.sort([json.loads(l)['enrollment_day']/365.25 for l in p.read_text().splitlines()])
  ax.step(np.r_[0,years],np.arange(len(years)+1),where='post',color=SYNTH,lw=1.15,ls=ls,label=f'{rate}/year: {years[-1]:.1f} years')
 ax.axhline(target,color=UNKNOWN,ls=':',lw=.8);ax.text(.2,target+10,f'Target: {target}',fontsize=7)
 ax.set(xlim=(0,11),ylim=(0,460),xlabel='Years from first enrolment',ylabel='Participants enrolled');ax.legend(loc='lower right',fontsize=7)
 ax=f.add_axes([.625,.13,.315,.285]);t=np.linspace(0,8,300)
 ax.plot(t,100*(om['cure_fraction']+(1-om['cure_fraction'])*np.exp(-om['failure_rate_per_year']*t)),color=FITTED,lw=1.2)
 for pos,val,ci,col,mk,label in [(4.88,ctl['predicted'],ctl['predicted_90'],FITTED,'o','Predicted: 90% interval'),(5.12,ctl['observed'],ctl['observed_95ci'],OBSERVED,'s','Observed: 95% CI')]:ax.errorbar(pos,val,yerr=[[val-ci[0]],[ci[1]-val]],fmt=mk,ms=4,color=col,capsize=2,lw=1,label=label)
 ax.set(xlim=(0,8),ylim=(0,100),xlabel='Years',ylabel='Event-free survival (%)');ax.legend(loc='lower left',fontsize=6.8)
 save(f,'fig3_walkthrough_ACNS0332')

PRED_STAGES=['studyspec','protocol_facts','population','eligibility','cohorts','outcomes','results','planning','safety','outputs']
def stage_lock_times(b):
 v=latest(b,'planning_comparison').name.rsplit('_v',1)[1];out={}
 for s in PRED_STAGES:
  p=LOCK/b/f'{s}_v{v}'
  if not p.exists():p=latest(b,s) if list((LOCK/b).glob(f'{s}_v*')) else None
  if p is not None:out[s]=datetime.fromisoformat(load(p/'lock.json')['locked_at'])
 return out

def fig4_blind_timeline():
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
  'Development studies: every prediction stage was frozen before registry results were retrieved.')
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
 for x,txt in zip(columns,['Final prediction\nfreeze','Results\nretrieved','First comparison\nrecorded','Time before\nretrieval']):
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

def fig5_accrual():
 f=figure(6.0,'Recruitment forecasts and observed trial outcomes','Three development studies; forecasts were frozen before results were read')
 heading(f,.055,.87,'A','Recruitment rate');ax=f.add_axes([.27,.53,.67,.29]);failure=[]
 for i,b in enumerate(BLIND):
  d=load(latest(b,'planning_comparison')/'planning_comparison.json');y=2-i;q=d['historical_model']['predicted_patients_per_year'];a=d['actual'];score=a['enrolled']>=5
  ax.plot([q['q10'],q['q90']],[y]*2,color=FITTED,lw=1.2);ax.plot([q['q25'],q['q75']],[y]*2,color=FITTED,lw=4)
  ax.plot(q['median'],y,'o',color=FITTED,mfc='white',ms=5,mew=1.2);ax.text(q['median'],y+.16,f"{q['median']:.1f}",ha='center',color=FITTED,fontsize=7.5)
  for sc in d['protocol_scenarios']:
   if sc.get('patients_per_year'):
    v=sc['patients_per_year'];ax.plot(v,y,'D',color=PROTOCOL,ms=5);ax.text(v,y+.16,f'{v:g}',ha='center',color=PROTOCOL,fontsize=7.5)
  if score:
   v=d['historical_model']['observed_rate_per_year_lower_bound'];ax.plot(v,y,'>',color=OBSERVED,ms=6);ax.text(v,y-.20,f'>= {v:.1f}',ha='center',fontsize=7)
  else:ax.text(.46,y-.21,'Not evaluated: one participant',fontsize=7,color=SLATE)
  fm=d['failure_model'];failure.append(fm)
 ax.set_xscale('log');ax.set_xlim(.4,300);ax.set_xticks([1,10,100]);ax.xaxis.set_major_formatter(mpl.ticker.ScalarFormatter());ax.set_ylim(-.6,2.6)
 ax.set_yticks([2,1,0],['Study 1\n7 enrolled','Study 2\n57 enrolled','Study 3\n1 enrolled']);ax.tick_params(axis='y',length=0,pad=8);ax.spines['left'].set_visible(False)
 ax.set_xlabel('Participants per year (log scale)')
 handles=[Line2D([],[],color=FITTED,lw=4,label='50% predictive interval'),Line2D([],[],color=FITTED,lw=1.2,label='80% predictive interval'),Line2D([],[],marker='D',color=PROTOCOL,ls='',label='Protocol assumption'),Line2D([],[],marker='>',color=OBSERVED,ls='',label='Observed lower bound')]
 f.legend(handles=handles,loc='center',bbox_to_anchor=(.51,.415),ncol=2,fontsize=7)
 heading(f,.055,.335,'B','Probability assigned to the outcome that occurred');ax=f.add_axes([.37,.105,.57,.195])
 outcomes={'terminated_other':'Terminated: other reason','completed':'Completed','terminated_accrual':'Terminated: poor accrual'}
 for i,fm in enumerate(failure):
  y=2-i;p=fm['predicted_probability'];base=fm['base_rate']
  ax.plot([p,base],[y,y],color='#B7C1CA',lw=1.5);ax.plot(base,y,'s',color=UNKNOWN,ms=5);ax.plot(p,y,'o',color=FITTED,ms=5)
  ax.text(max(p,base)+.045,y,f'{p:.0%} / {base:.0%}',va='center',fontsize=7.3)
 ax.set_yticks([2,1,0],[f"Study {i+1}: {outcomes.get(v['observed_outcome'],v['observed_outcome'].replace('_',' '))}" for i,v in enumerate(failure)],fontsize=7.4);percent(ax);ax.set_ylim(-.55,2.55);ax.set_xlabel('Probability of the observed outcome')
 f.legend(handles=[Line2D([],[],marker='o',ls='',color=FITTED,label='Model probability'),Line2D([],[],marker='s',ls='',color=UNKNOWN,label='Historical base rate')],loc='lower center',bbox_to_anchor=(.53,.005),ncol=2,fontsize=7)
 save(f,'fig5_accrual_blind')

def parse_scorecard():
 return load(ROOT/'data/validation/scorecard.json')['components']

def fig6_calibration():
 rows=parse_scorecard();f=figure(6.1,'Component calibration and predictive performance','Evaluation units differ by component; survival is an internal consistency check.')
 heading(f,.055,.87,'A','Observed coverage at each nominal interval level')
 a=canvas(f,[.055,.405,.89,.43]);components=[
 ('accrual rate (patients/month)','Accrual rate','658 trials'),('adverse events: reported counts','Listed adverse-event counts','31,267 observations'),
 ('adverse events: serious events reported absent','Serious events reported absent','2,641 observations'),('baseline: mean age','Mean age','80 studies'),('baseline: share female','Female proportion','80 studies'),('outcome proportions (response, safety)','Outcome proportions','312 evaluated units'),('survival (arm medians, landmarks)','Survival: consistency check','355 summaries')]
 levels=[.5,.8,.9,.95];xx=[.61,.72,.83,.94]
 a.text(0,.94,'Component',fontweight='bold',fontsize=8);a.text(.37,.94,'Evaluation units',fontweight='bold',fontsize=7.5)
 for x,l in zip(xx,levels):a.text(x,.94,f'{l:.0%}',ha='center',fontweight='bold',fontsize=8)
 for i,(key,label,note) in enumerate(components):
  y=.82-i*.115;a.axhline(y-.057,color='#E5EAF0',lw=.5);a.text(0,y,label,va='center',fontsize=7.5);a.text(.37,y,note,va='center',fontsize=7)
  rr=[r for r in rows if r['component']==key]
  for x,l in zip(xx,levels):
   r=next((r for r in rr if r['nominal'] is not None and abs(r['nominal']-l)<1e-5),None)
   a.text(x,y,f"{r['coverage']:.0%}" if r else '-',ha='center',va='center',fontsize=8,color=FITTED if r else UNKNOWN)
 heading(f,.055,.33,'B','Adverse-event predictive score on held-out trials')
 a=f.add_axes([.40,.10,.49,.19]);m=load(ROOT/'data/safety_asset_v3_1/manifest.json')['validation']['listed']['mean_log_predictive_probability']
 t0=load(ROOT/'data/safety_asset_t0/manifest.json')['validation']['listed']['mean_log_predictive_probability']
 vals=[m['v3_uncalibrated'],m['v3'],t0['v3']]
 labels=['Before calibration','After calibration','Evidence frozen at 2024']
 for i,(label,v) in enumerate(zip(labels,vals)):
  y=2-i;a.plot([-3,v],[y,y],color='#E7E2F0',lw=4);a.plot(v,y,'o',color=FITTED,ms=5);a.text(v+.06,y,f'{v:.2f}',va='center',fontsize=8)
 a.set_yticks([2,1,0],labels,fontsize=8);a.tick_params(axis='y',length=0);a.spines['left'].set_visible(False);a.set(xlim=(-3,-1.5),ylim=(-.6,2.6),xlabel='Mean log predictive score (higher is better)')
 a.set_xticks([-3,-2.5,-2,-1.5]);a.grid(axis='x',color='#E5EAF0',lw=.5)
 f.text(.055,.025,'Held-out trials were never used for fitting. The 2024 model is fitted only on trials whose evidence predates 1 January 2024.',fontsize=7,color=SLATE)
 save(f,'fig6_calibration')

def event_name(row):
 s=row['term'].replace('_',' ')
 s={'alanine aminotransferase increased':'ALT increased','aspartate aminotransferase increased':'AST increased'}.get(s,s)
 if row['seriousness']=='serious':s+=' [serious]'
 elif row['seriousness']=='grade clinically significant or severe (ie, grade 3)':s+=' [grade 3]'
 elif row['seriousness'].startswith('grade ') and 'all grades' not in row['seriousness']:s+=' ['+row['seriousness']+']'
 return s[0].upper()+s[1:]

def fig7_blind_events():
 data=[]
 for b in ['BLIND_1','BLIND_2']:
  d=load(latest(b,'safety_comparison')/'safety_comparison.json');rows=[r for r in d['rows'] if r['observed_listed']];assert len(rows)==d['matched_terms']
  data.append((b,d,sorted(rows,key=lambda r:r['predicted_rate'],reverse=True)))
 f=figure(9.0,'Adverse-event predictions in the development studies','Matched reported events only; each interval uses the registry population at risk.')
 # Two columns retain every comparison. Equal row spacing; the shorter panel leaves room for notes.
 bounds=[(.27,.56,.23,.30),(.75,.14,.20,.72)]
 for k,((b,d,rows),(x,y,w,h)) in enumerate(zip(data,bounds)):
  heading(f,.055 if k==0 else .57,.89,'AB'[k],f'Study {k+1}: {d["registry_at_risk"]} at risk')
  f.text(.055 if k==0 else .57,.87,f'{d["matched_inside_90"]}/{len(rows)} inside the 90% interval',fontsize=7.6,color=SLATE)
  ax=f.add_axes([x,y,w,h]);n=d['registry_at_risk']
  for i,r in enumerate(rows):
   yy=len(rows)-1-i;lo,hi=r['predicted_90'];ax.plot([lo/n,hi/n],[yy,yy],color=FITTED,lw=2.4,alpha=.30)
   ax.plot(r['predicted_median']/n,yy,'|',color=FITTED,ms=6,mew=1.1)
   outside=not r['inside_90'];ax.plot(r['observed']/n,yy,'D' if outside else 'o',ms=4,color=PROTOCOL if outside else OBSERVED,mec='white',mew=.35)
  ax.set_yticks(range(len(rows)),[event_name(r) for r in rows][::-1],fontsize=7.1);percent(ax);ax.set_xlim(-.03,1.03);ax.set_ylim(-.6,len(rows)-.4);ax.set_xlabel('Participants affected',fontsize=7.6)
  ax.set_xticks([0,.5,1])
 f.text(.055,.48,'Reading the figure',fontweight='bold',fontsize=9)
 notes='Bars: 90% predictive intervals\nTicks: predicted median counts\nCircles: reported event counts\nDiamonds: observations outside the interval\n\n[serious] identifies serious adverse events.\nALT: alanine aminotransferase\nAST: aspartate aminotransferase\n\nRepeated terms with different qualifiers\nremain separate comparisons.'
 f.text(.055,.45,notes,va='top',fontsize=7.6,linespacing=1.55)
 f.text(.055,.065,'Study 1: NCT04003610     Study 2: NCT04205799',fontsize=7.6,color=SLATE)
 f.text(.055,.04,'Broad intervals limit the interpretation of high coverage; the event comparisons are not independent trials.',fontsize=7,color=SLATE)
 save(f,'fig7_blind_adverse_events')

def wilson(k,n,z=1.96):
 p=k/n;d=1+z*z/n;c=(p+z*z/(2*n))/d;h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
 return c-h,c+h

def subgroup_label(dim,name):
 name=name.replace('PHASE1+PHASE2','Phase I/II').replace('PHASE2','Phase II').replace('PHASE3','Phase III').replace('_',' ')
 if dim=='phase':return name
 if dim=='age group':return 'Age: '+name
 if dim=='drug classes':return 'Different drug classes' if name=='not overlapping' else 'Drug classes: '+name
 return dim.replace('_',' ')+': '+name

def fig8_informative():
 f=figure(7.8,'Aggregate safety and control-survival estimates','Historical subgroup estimates compared with outcomes in the development studies')
 for k,b in enumerate(['BLIND_1','BLIND_2']):
  est=load(latest(b,'outputs')/'trial_outputs.json')['feasibility']['subgroup_estimates'];sa=load(latest(b,'safety_comparison')/'safety_comparison.json')['aggregate']['serious']
  arm=next(iter(est['arms'].values()))['serious_adverse_event'];entries=[('Selected subgroup',arm['headline'],True)]
  for dim,groups in arm['breakdown'].items():
   for name,g in groups.items():
    if g!=arm['headline']:entries.append((subgroup_label(dim,name),g,False))
  hy=.87-k*.295;heading(f,.055,hy,'AB'[k],f'Study {k+1}: any serious adverse event')
  kk,nn=sa['registry_affected'],sa['at_risk'];f.text(.055,hy-.028,f"Estimated {arm['headline']['estimate']:.1%}; observed {kk}/{nn} ({kk/nn:.1%})",fontsize=8,color=SLATE)
  ax=f.add_axes([.43,hy-.236,.51,.187]);wl,wh=wilson(kk,nn);ax.axvspan(wl,wh,color='#EEF0F2',lw=0);ax.axvline(kk/nn,color=OBSERVED,lw=1)
  for i,(label,g,head) in enumerate(entries):
   y=len(entries)-1-i;c=FITTED if head else '#9B8CAF';ax.plot(g['single_trial_80'],[y,y],color=c,lw=.8)
   ax.plot(g['ci95'],[y,y],color=c,lw=2.5 if head else 1.5);ax.plot(g['estimate'],y,'o',ms=4,color=c,mec='white',mew=.5)
  ax.set_yticks(range(len(entries)),[f"{label} ({g['studies']} studies)" for label,g,_ in entries][::-1],fontsize=7.3)
  percent(ax);ax.set_ylim(-.65,len(entries)-.35)
 heading(f,.055,.285,'C','Study 1: control-arm progression-free survival')
 mc=load(latest('BLIND_1','median_comparison')/'median_comparison.json')['items'][0];p=mc['predicted_control'];ctl=next(g for g in mc['groups'] if g['group']==mc['control_group'])
 ax=f.add_axes([.43,.137,.51,.105]);lo,hi=p['ci95_months'];v=p['median_months']
 ax.errorbar(v,1,xerr=[[v-lo],[hi-v]],fmt='o',color=FITTED,ms=4,capsize=3,lw=1.2)
 ax.text(hi+.18,1,f'{v:.1f} months; {p["studies"]} studies',va='center',fontsize=7)
 v=ctl['median_months'];ax.plot(v,0,'s',color=OBSERVED,ms=4);ax.annotate('',xy=(7.85,0),xytext=(ctl['ci'][0],0),arrowprops={'arrowstyle':'-|>','color':OBSERVED,'lw':1})
 ax.plot([ctl['ci'][0]]*2,[-.12,.12],color=OBSERVED,lw=1)
 ax.text(3.1,-.33,f'{v:.1f} months; n = {int(ctl["participants"])}; upper CI not reached',fontsize=7)
 ax.set(xlim=(0,8),ylim=(-.7,1.6),xlabel='Median progression-free survival (months)');ax.set_yticks([1,0],['Historical estimate','Registry control arm']);ax.tick_params(axis='y',length=0);ax.spines['left'].set_visible(False)
 handles=[Line2D([],[],color=FITTED,lw=2.5,label='95% CI of the subgroup mean'),Line2D([],[],color=FITTED,lw=.8,label='80% range for a new trial'),Line2D([],[],color=OBSERVED,lw=1,label='Observed proportion'),Patch(fc='#EEF0F2',label='Observed 95% Wilson CI')]
 f.legend(handles=handles,loc='lower center',bbox_to_anchor=(.52,.017),ncol=2,fontsize=7)
 save(f,'fig8_blind_informative_estimates')

SHOW='NCT03859427'
def show_lock(kind,version='1.3.0'):
 return LOCK/SHOW/f'{kind}_v{version}'

def fig9_temporal():
 ni=load(show_lock('results')/'ni_results.json');reg=load(ROOT/'data/holdout_comparison'/f'{SHOW}.json')
 plan=load(show_lock('planning_comparison')/'planning_comparison.json');saf=load(show_lock('safety_comparison','1.3.0.3')/'safety_comparison.json')
 order=load(ROOT/'data/validation'/f'{SHOW}_unblinding.json');assert order['order_ok']
 om=next(o for o in reg['resultsSection']['outcomeMeasuresModule']['outcomeMeasures'] if o['type']=='PRIMARY')
 den={c['groupId']:int(c['value']) for d in om['denoms'] for c in d['counts']}
 val={m['groupId']:float(m['value']) for c in om['classes'] for cat in c['categories'] for m in cat['measurements']}
 title={g['id']:g['title'] for g in om['groups']};an=om['analyses'][0]
 f=figure(9.6,'Temporal test: a phase III trial predicted from its protocol alone',
  f'{SHOW} | once- vs twice-weekly carfilzomib regimen in relapsed myeloma | evidence frozen at 1 January 2024')
 heading(f,.055,.885,'A','Response rate by arm')
 ax=f.add_axes([.25,.745,.24,.11]);lo,hi=ni['predicted_response']['observed_rate_90_at_n'];med=ni['predicted_response']['control_true_rate']['median']
 rows=[(g,('Twice-weekly (control)' if 'twice' in title[g].lower() else 'Once-weekly')) for g in sorted(val)]
 for i,(g,label) in enumerate(rows):
  y=1-i;ax.plot([lo,hi],[y,y],color=FITTED,lw=5,alpha=.3,solid_capstyle='butt');ax.plot(med,y,'|',color=FITTED,ms=8,mew=1.3)
  k=round(val[g]/100*den[g]);wl,wh=wilson(k,den[g]);ax.plot([wl,wh],[y,y],color=OBSERVED,lw=.9);ax.plot(val[g]/100,y,'o',color=OBSERVED,ms=4.5,mec='white',mew=.4)
 ax.set_yticks([1,0],[r[1] for r in rows],fontsize=7.4);ax.set_xlim(.6,1);ax.xaxis.set_major_formatter(mpl.ticker.PercentFormatter(1,decimals=0))
 ax.set_ylim(-.6,1.6);ax.tick_params(axis='y',length=0);ax.spines['left'].set_visible(False);ax.grid(axis='x',color='#E5EAF0',lw=.5);ax.set_xlabel('Overall response rate',fontsize=7.5)
 f.text(.055,.69,'Band: 90% predictive range of the observed rate. Circle: reported rate with 95% CI.',fontsize=6.8,color=SLATE)
 heading(f,.565,.885,'B','Chance of showing non-inferiority')
 ax=f.add_axes([.64,.745,.30,.11]);c=ni['p_success_curve'];ax.plot([r['rr'] for r in c],[r['p_noninferior'] for r in c],'-o',color=FITTED,ms=3,lw=1.1)
 rr=float(an['paramValue']);ax.axvline(rr,color=OBSERVED,ls=(0,(3,2)),lw=.9);ax.text(rr-.004,.93,f'Observed ratio {rr:.3f}',ha='right',va='top',fontsize=6.8)
 ax.set(xlim=(.79,1.06),ylim=(0,1));ax.set_xlabel('True response-rate ratio (once / twice weekly)',fontsize=7.3);ax.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(1,decimals=0))
 ax.set_ylabel('Probability',fontsize=7.3);ax.grid(color='#E5EAF0',lw=.5)
 f.text(.565,.69,f"Reported: not non-inferior (one-sided p = {float(an['pValue']):.3f}).",fontsize=6.8,color=SLATE)
 f.text(.565,.672,'Model at the observed ratio: about 1 in 4.',fontsize=6.8,color=SLATE)
 heading(f,.055,.625,'C','Recruitment rate')
 ax=f.add_axes([.25,.545,.24,.05]);hm=plan['historical_model'];q=hm['predicted_patients_per_year']
 ax.plot([q['q10'],q['q90']],[0,0],color=FITTED,lw=1.2);ax.plot([q['q25'],q['q75']],[0,0],color=FITTED,lw=4);ax.plot(q['median'],0,'o',color=FITTED,mfc='white',ms=5,mew=1.2)
 ob=hm['observed_rate_per_year_lower_bound'];ax.plot(ob,0,'>',color=OBSERVED,ms=6)
 ax.set_xscale('log');ax.set_xlim(20,600);ax.set_xticks([20,50,100,200,500]);ax.xaxis.set_major_formatter(mpl.ticker.ScalarFormatter());ax.xaxis.set_minor_formatter(mpl.ticker.NullFormatter());ax.set_yticks([]);ax.spines['left'].set_visible(False)
 ax.set_ylim(-1,1);ax.set_xlabel('Participants per year (log scale)',fontsize=7.3)
 fm=plan['failure_model']
 f.text(.055,.47,f"Predicted {q['median']:.0f}/year (80% range {q['q10']:.0f}-{q['q90']:.0f}); observed at least {ob:.0f}/year.",fontsize=6.9,color=SLATE)
 f.text(.055,.452,f"Trial completed; predicted completion {fm['predicted_probability']:.0%} (historical base rate {fm['base_rate']:.0%}).",fontsize=6.9,color=SLATE)
 heading(f,.565,.625,'D','Adverse events (matched terms)')
 rows=sorted([r for r in saf['rows'] if r.get('observed_listed') and r['seriousness']!='serious'],key=lambda r:r['predicted_rate'],reverse=True)[:12]
 ax=f.add_axes([.74,.415,.20,.175]);n=saf['registry_at_risk']
 for i,r in enumerate(rows):
  y=len(rows)-1-i;lo2,hi2=r['predicted_90'];ax.plot([lo2/n,hi2/n],[y,y],color=FITTED,lw=2.4,alpha=.3);ax.plot(r['predicted_median']/n,y,'|',color=FITTED,ms=6,mew=1.1)
  out=not r['inside_90'];ax.plot(r['observed']/n,y,'D' if out else 'o',ms=3.8,color=PROTOCOL if out else OBSERVED,mec='white',mew=.35)
 ax.set_yticks(range(len(rows)),[event_name(r) for r in rows][::-1],fontsize=6.8);percent(ax);ax.set_xticks([0,.5,1]);ax.set_xlabel('Participants affected',fontsize=7.3)
 f.text(.565,.598,f"{saf['matched_inside_90']} of {saf['matched_terms']} matched events inside the 90% interval",fontsize=6.8,color=SLATE)
 heading(f,.055,.345,'E','Patient journey: locked prediction, correction and observation')
 jl=load(show_lock('journey')/'journey_summary.json');jr=load(ROOT/'data/trial/temporal'/SHOW/'retrospective_journey_L018/journey_summary.json')
 js,rj=jl['summary'],jr['summary']
 pf=reg['resultsSection']['participantFlowModule']['periods'][0];ms={m['type']:sum(int(a['numSubjects']) for a in m['achievements']) for m in pf['milestones']}
 left=sum(int(a['numSubjects']) for d in pf['dropWithdraws'] if d['type'] in ('Withdrawal by Subject','Lost to Follow-up','Decision by sponsor') for a in d['reasons'])
 pfs=next(o for o in reg['resultsSection']['outcomeMeasuresModule']['outcomeMeasures'] if 'Progression-free Survival (PFS) Rate at 12' in o['title'])
 pobs=np.mean([float(m['value']) for c in pfs['classes'] for cat in c['categories'] for m in cat['measurements']])/100
 wd='withdrawal (subject, loss to follow-up or physician decision)';n0=js['subjects']
 lockrate=jl['progression']['ARM1']['value']['rate_per_year'];retro=jr['progression']['ARM1']['value']['rate_per_year']
 items=[('Left the study (non-medical reasons)',js['end_of_treatment_reasons'].get(wd,0)/n0,rj['end_of_treatment_reasons'].get(wd,0)/n0,left/ms['STARTED']),
  ('Completed 12 treatment cycles',js['end_of_treatment_reasons'].get('completed planned treatment',0)/n0,rj['end_of_treatment_reasons'].get('completed planned treatment',0)/n0,ms['Completed 12 Cycles Carfilzomib']/ms['STARTED']),
  ('Progression-free at 12 months',math.exp(-lockrate),math.exp(-retro),pobs)]
 ax=f.add_axes([.40,.135,.54,.175])
 for i,(label,a1,a2,o) in enumerate(items):
  y=2-i;ax.plot([min(a1,a2,o),max(a1,a2,o)],[y,y],color='#DDE3E9',lw=1.2)
  ax.plot(a1,y,'o',color=PROTOCOL,ms=5.5);ax.plot(a2,y,'o',color=FITTED,mfc='white',mew=1.3,ms=5.5);ax.plot(o,y,'s',color=OBSERVED,ms=5)
 ax.set_yticks([2,1,0],[x[0] for x in items],fontsize=7.4);percent(ax);ax.set_ylim(-.6,2.6);ax.set_xlabel('Share of participants',fontsize=7.3)
 f.legend(handles=[Line2D([],[],marker='o',ls='',color=PROTOCOL,label='Locked prediction'),Line2D([],[],marker='o',ls='',color=FITTED,mfc='white',label='After correction (retrospective)'),
  Line2D([],[],marker='s',ls='',color=OBSERVED,label='Registry')],loc='lower center',bbox_to_anchor=(.55,.058),fontsize=7,ncol=3)
 f.text(.055,.045,f"Predictions frozen {order['locked_at_latest'][11:19]} UTC; results retrieved {order['fetched_at'][11:19]} UTC on the same day.",fontsize=6.8,color=SLATE)
 f.text(.055,.025,"Correction after unblinding: the protocol's own progression figure for the regimen replaced a cross-regimen average.",fontsize=6.8,color=SLATE)
 save(f,'fig9_temporal_showcase')

def fig10_trace(subject='S0198'):
 import csv
 D=show_lock('journey')
 def rows(name):
  p=D/f'{name}.csv';READS.add(p)
  with open(p,encoding='utf-8') as fh:return [r for r in csv.DictReader(fh) if r['USUBJID']==subject]
 dm=rows('dm')[0];ex=rows('ex');ae=rows('ae');lb=rows('lb');rs=rows('rs');ds=rows('ds')
 end=max([int(float(r['RSDY'])) for r in rs]+[int(float(r['DSSTDY'])) for r in ds])
 arm='Twice-weekly' if dm['ARMCD']=='ARM2' else 'Once-weekly'
 f=figure(5.2,'One simulated participant, day by day',f"Arm: {arm} | age {float(dm['AGE']):.0f}, {dm['SEX']} | every element carries its source")
 ax=f.add_axes([.25,.27,.70,.56]);lanes=['Screening labs','Dosing (by cycle)','Adverse events','Disease assessment','End of treatment']
 for i in range(5):ax.axhline(4-i,color='#EEF1F4',lw=9,zorder=0)
 for r in lb:
  if r['VISIT']=='SCREENING':ax.plot(float(r['LBDY']),4,'s',ms=5,color=UNKNOWN)
 for c in sorted({int(r['CYCLE']) for r in ex}):
  ax.barh(3,26,left=(c-1)*28+1,height=.36,color=PALE[SLATE],ec=PROTOCOL,lw=.7)
 for r in ae:
  s0=float(r['AESTDY']);e0=float(r['AEENDY'] or r['AESTDY']);g=int(r['AETOXGR'] or 1)
  ax.plot([s0,max(e0,s0+1.5)],[2,2],color=EVIDENCE,lw=1.5+g*1.2,solid_capstyle='butt')
 for r in rs:
  pd=r['RSORRES'].startswith('progressive');ax.plot(float(r['RSDY']),1,'D' if pd else 'o',ms=5.5 if pd else 4.5,color=OBSERVED if pd else UNKNOWN,mec='white',mew=.4)
 for r in ds:ax.plot(float(r['DSSTDY']),0,'X',ms=7,color=OBSERVED);ax.text(float(r['DSSTDY'])+5,0,r['DSDECOD'],va='center',fontsize=7.2)
 ax.set_yticks(range(5),lanes[::-1],fontsize=7.8);ax.tick_params(axis='y',length=0);ax.spines['left'].set_visible(False)
 ax.set_xlim(-35,end+70);ax.set_xticks([t for t in range(0,end+71,28) if t<=end+70]);ax.set_ylim(-.6,4.6);ax.set_xlabel('Study day (day 1 = first dose)');ax.grid(axis='x',color='#E5EAF0',lw=.5)
 handles=[Patch(fc=PALE[SLATE],ec=PROTOCOL,label='Protocol: cycle schedule and doses'),Line2D([],[],color=EVIDENCE,lw=3,label='Evidence: adverse events (thicker = higher grade)'),
  Line2D([],[],marker='s',ls='',color=UNKNOWN,label='Assumption: labs normal (no evidence)'),Line2D([],[],marker='D',ls='',color=OBSERVED,label='Progression: evidence rate, exponential')]
 f.legend(handles=handles,loc='lower left',bbox_to_anchor=(.05,.02),ncol=2,fontsize=6.9)
 save(f,'fig10_patient_trace')

def fig11_population_sae():
 import csv
 D=LOCK/'BLIND_1'/'outputs_v1.2.0'
 def rows(name):
  p=D/name;READS.add(p)
  with open(p,encoding='utf-8') as fh:return list(csv.DictReader(fh))
 adsl=rows('adsl.csv');est=load(D/'trial_outputs.json')['feasibility']['subgroup_estimates']['arms']
 reg=load(ROOT/'data/holdout_comparison/NCT04003610.json')['resultsSection']
 ages=np.array([float(r['AGE']) for r in adsl]);inband=int(np.sum((ages>=57)&(ages<=84)))
 soc=[r for r in adsl if r['ARM'] in ('ARM3','ARM4')];n=len(soc)
 sim={'Women':sum(r['SEX']=='female' for r in soc)/n,'Asian':sum(r['RACE']=='asian' for r in soc)/n,'White':sum(r['RACE']=='white' for r in soc)/n}
 bm={m['title']:m for m in reg['baselineCharacteristicsModule']['measures']}
 def bval(title,cat):
  m=next(v for k,v in bm.items() if k.startswith(title))
  return next(int(x['value']) for c in m['classes'] for ct in c['categories'] if ct.get('title')==cat for x in ct['measurements'] if x['groupId']=='BG002')
 real={'Women':bval('Sex','Female')/6,'Asian':bval('Race','Asian')/6,'White':bval('Race','White')/6}
 ev={g['id']:(g['seriousNumAffected'],g['seriousNumAtRisk']) for g in reg['adverseEventsModule']['eventGroups']}
 f=figure(8.4,'Simulated cohort, enrolled participants and arm-matched serious adverse events',
  'NCT04003610 development study | 372 simulated participants compared with 7 participants enrolled in the trial')
 heading(f,.055,.885,'A','Age distribution of the simulated cohort')
 ax=f.add_axes([.10,.64,.84,.2]);ax.hist(ages,bins=np.arange(0,90,3),color=SYNTH,alpha=.75,ec='white',lw=.4)
 ax.axvspan(57,84,color=PROTOCOL,alpha=.10,lw=0);ax.text(70.5,ax.get_ylim()[1]*.9,'Enrolled trial population:\n7/7 aged 57-84',ha='center',va='top',fontsize=7.3,color=PROTOCOL)
 ax.set(xlim=(0,88),xlabel='Age (years)',ylabel='Simulated participants');ax.grid(axis='y',color='#E5EAF0',lw=.5)
 f.text(.10,.565,f'Simulated cohort: mean age {ages.mean():.1f} years; {inband} of {len(ages)} ({inband/len(ages):.0%}) aged 57-84; {int(np.sum(ages<18))} under 18.',fontsize=7.3,color=SLATE)
 f.text(.10,.545,'Drawn from simulated patients not ruled out by the checkable criteria; 37 criteria per patient, including the age limit, could not be checked.',fontsize=7.0,color=SLATE)
 heading(f,.055,.51,'B','Standard-care participants')
 ax=f.add_axes([.10,.10,.34,.37]);keys=list(sim);x=np.arange(len(keys))
 ax.bar(x-.19,[sim[k] for k in keys],.36,color=SYNTH,label=f'Simulated (n = {n})')
 ax.bar(x+.19,[real[k] for k in keys],.36,color=OBSERVED,label='Real (n = 6)')
 for i,k in enumerate(keys):
  ax.text(i-.19,sim[k]+.02,f'{sim[k]:.0%}',ha='center',fontsize=7);ax.text(i+.19,real[k]+.02,f'{real[k]:.0%}',ha='center',fontsize=7)
 ax.set_xticks(x,keys);ax.set_ylim(0,1.05);ax.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(1,decimals=0));ax.grid(axis='y',color='#E5EAF0',lw=.5)
 ax.legend(loc='upper left',fontsize=6.8)
 heading(f,.53,.51,'C','Any serious adverse event, by arm')
 ax=f.add_axes([.66,.36,.18,.11])
 arms=[('Pemigatinib +\npembrolizumab','ARM1','EG001'),('Standard care','ARM3','EG002')]
 draws=[]
 rng=np.random.default_rng(20260930)
 for i,(label,arm,g) in enumerate(arms):
  h=est[arm]['serious_adverse_event']['headline'];y=1-i;lo,hi=h['single_trial_80']
  ax.plot([lo,hi],[y,y],color=FITTED,lw=4,alpha=.35,solid_capstyle='butt');ax.plot(h['estimate'],y,'|',color=FITTED,ms=9,mew=1.4)
  k,m=ev[g];wl,wh=wilson(k,m);ax.plot([wl,wh],[y-.18]*2,color=OBSERVED,lw=.9);ax.plot(k/m,y-.18,'o',color=OBSERVED,ms=4.5,mec='white',mew=.4)
  ax.text(1.03,y-.05,f"Predicted {h['estimate']:.1%};\nobserved {k}/{m}",fontsize=6.9,va='center',transform=ax.get_yaxis_transform())
  a,b=math.log(lo/(1-lo)),math.log(hi/(1-hi));mu,sd=(a+b)/2,(b-a)/(2*1.2816)
  draws.append((m,1/(1+np.exp(-rng.normal(mu,sd,200000)))))
 ax.set_yticks([1,0],[a[0] for a in arms],fontsize=7);percent(ax);ax.set_ylim(-.6,1.5);ax.set_xticks([0,.5,1])
 x7=sum(rng.binomial(m,p) for m,p in draws);obs=sum(ev[g][0] for _,_,g in arms)
 ax=f.add_axes([.60,.10,.34,.14]);k=np.arange(8);pk=np.array([np.mean(x7==i) for i in k])
 ax.bar(k,pk,color=[OBSERVED if i==obs else '#C9C1DA' for i in k],width=.7)
 ax.set_xticks(k);ax.set_xlabel('Participants with a serious event, of 7 (1 + 6)',fontsize=7.3);ax.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(1,decimals=0))
 ax.grid(axis='y',color='#E5EAF0',lw=.5)
 f.text(.53,.275,f'Realised arms: expected {x7.mean():.2f} of 7; observed {obs}; P(at most {obs}) = {np.mean(x7<=obs):.2f}',fontsize=7.2,color=SLATE)
 f.legend(handles=[Line2D([],[],color=FITTED,lw=4,alpha=.35,label='80% range for a single trial'),Line2D([],[],marker='|',ls='',color=FITTED,ms=8,label='Predicted'),
  Line2D([],[],marker='o',ls='',color=OBSERVED,label='Observed (95% CI)')],loc='center',bbox_to_anchor=(.74,.315),ncol=3,fontsize=6.6,handlelength=1.4,columnspacing=.9)
 f.text(.055,.035,"Simulated standard care pools the simulation's two standard-care arms to match the registry group (gemcitabine-carboplatin or pembrolizumab).",fontsize=6.6,color=SLATE)
 f.text(.055,.017,'Serious-event probabilities depend on the treatment arm only, not on age, sex or race. With realised arm sizes of 1 and 6, these comparisons are descriptive.',fontsize=6.6,color=SLATE)
 save(f,'fig11_population_and_arm_sae')

if __name__=='__main__':
 for fn in [fig1_pipeline,fig2_evidence_lane,fig3_walkthrough,fig4_blind_timeline,fig5_accrual,fig6_calibration,fig7_blind_events,fig8_informative,fig9_temporal,fig10_trace,fig11_population_sae]:fn()
 sources=[{'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(READS)]
 (OUT/'figure_provenance.json').write_text(json.dumps({'sources':sources,'running_example':{'study':'NCT00091572','registry_group':'EG000','evidence_row':'d9b934b17937e424','parameter_id':'3b1473de78a0a559'},'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'note':'Technical identifiers and versions are retained here and in the source artifacts, not in figure labels.'},indent=2),encoding='utf-8')
 audit_path=ROOT/'tmp/figure_revision/layout_audit.json'
 audit_path.parent.mkdir(parents=True,exist_ok=True)
 audit_path.write_text(json.dumps(AUDIT,indent=2),encoding='utf-8')
