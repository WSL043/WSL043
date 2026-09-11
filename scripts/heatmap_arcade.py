#!/usr/bin/env python3
"""Contribution-driven simulations and GIF renderer. Never modifies source data.

Use ``python -m scripts.heatmap_data`` for daily generation. Coordinates and
levels come from a validated snapshot, not random decorative contributions.
"""
from __future__ import annotations
import argparse
import copy
import json
import math
import random
from collections import deque
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

COLS, ROWS = 53, 7
W, H, FPS, DURATION = 1040, 420, 20, 18.0
BG = '#0d1117'
TEXT, MUTED, LINE = '#e6edf3', '#8b949e', '#26323f'
GREEN = ['#161b22', '#0e4429', '#006d32', '#26a641', '#39d353']
CYAN, GOLD, RED = '#79e0f2', '#ffcc66', '#ff846f'
OWNER, DATA_LABEL, FOCUS_ZOOM = 'WSL043', 'SAVED SNAPSHOT', 1.85
SCENES = {
 'bomber': ('01', 'HEATMAP BOMBER', 'The green squares are the destructible walls.', GOLD),
 'miners': ('02', 'COMMIT MINERS', 'Your activity becomes ore. Two robots dig through it.', CYAN),
 'defense': ('03', 'CONTRIBUTION DEFENSE', 'Active days become towers. Empty days become the path.', '#b9a2ff'),
}
DIRS = [(1,0), (0,1), (-1,0), (0,-1)]


def load_snapshot(path: Path) -> tuple[dict, dict[tuple[int,int], int], set]:
    data = json.loads(path.read_text(encoding='utf-8'))
    global COLS
    if type(data.get('columns')) is not int or not 52 <= data['columns'] <= 54 or data.get('rows') != ROWS:
        raise ValueError('Expected 52-54 calendar weeks and 7 rows')
    COLS = data['columns']
    grid = {(x,y): 0 for x in range(COLS) for y in range(ROWS)}
    missing = set()
    for col, levels in data.get('active_columns', {}).items():
        x = int(col)
        if not 0 <= x < COLS or len(levels) != ROWS:
            raise ValueError('Invalid contribution column')
        for y, level in enumerate(levels):
            if level is None:
                missing.add((x,y))
            elif type(level) is not int or not 0 <= level <= 4:
                raise ValueError('Intensity must be an integer from 0 to 4, or null')
            else:
                grid[x,y] = level
    return data, grid, missing


def inside(p):
    # One explicit empty aisle around the graph; not additional contribution days.
    return -1 <= p[0] <= COLS and -1 <= p[1] <= ROWS


def bfs(start, grid):
    parents = {start: None}
    q = deque([start])
    while q:
        p = q.popleft()
        for dx,dy in DIRS:
            n = (p[0]+dx,p[1]+dy)
            if inside(n) and n not in parents and grid.get(n,0) == 0:
                parents[n] = p
                q.append(n)
    return parents


def path_to(parents, end):
    if end not in parents:
        return []
    out = [end]
    while parents[out[-1]] is not None:
        out.append(parents[out[-1]])
    return out[::-1]


def lerp(a,b,f): return a+(b-a)*f

def smooth(f):
    f = max(0.0,min(1.0,f))
    return f*f*(3-2*f)


def walk_pos(path, elapsed, step):
    if not path: return (0.,0.)
    f = max(0,elapsed/step)
    i = min(int(f),len(path)-1)
    j = min(i+1,len(path)-1)
    return tuple(lerp(path[i][k],path[j][k],min(1,f-i)) for k in (0,1))


def blast_at(center, grid, radius=3):
    cells = [center]
    hits = []
    for dx,dy in DIRS:
        for i in range(1,radius+1):
            n = (center[0]+dx*i, center[1]+dy*i)
            if not inside(n): break
            cells.append(n)
            if grid.get(n,0) > 0:
                hits.append(n)
                break
    return cells,hits


def plan_bomber(initial, seed):
    rng = random.Random(seed)
    grid = initial.copy()
    active = [p for p,v in grid.items() if v]
    start_x = max(-1, min((p[0] for p in active), default=43)-2)
    pos = (start_x,3)
    if grid.get(pos,0): pos=(start_x,-1)
    start_pos = pos
    time = 1.8
    events = []
    for _ in range(9):
        parents = bfs(pos,grid)
        choices=[]
        for p in parents:
            cells,hits=blast_at(p,grid)
            if not hits: continue
            route=path_to(parents,p)
            escapes=bfs(p,grid)
            safe=[v for v in escapes if v not in cells]
            if not safe: continue
            retreat=min((path_to(escapes,v) for v in safe),key=len)
            # Every candidate is reachable, every retreat ends outside the real blast.
            score=sum(1.0 + 1.8*(grid[h]==1) for h in hits)/(1+.11*(len(route)-1))
            choices.append((score+rng.random()*.4,p,route,retreat,cells,hits))
        if not choices: break
        _,p,route,retreat,cells,hits=max(choices,key=lambda a:a[0])
        plant=time+(len(route)-1)*.075
        escape_start=plant+.22
        explosion=max(plant+.95,escape_start+(len(retreat)-1)*.075+.1)
        if explosion>15.5: break
        hp={h:grid[h] for h in hits}
        for h in hits:grid[h]-=1
        events.append(dict(start=time,route=route,plant=plant,escape_start=escape_start,
                           retreat=retreat,explosion=explosion,cells=cells,hits=hits,hp=hp,
                           grid_before={k:v for k,v in initial.items()} if not events else None))
        # Storing the exact wall state makes independent path checks possible.
        before=grid.copy()
        for h in hits:before[h]+=1
        events[-1]['grid_before']=before
        pos=retreat[-1]
        time=explosion+.38
    return {'events':events,'start':start_pos,'final':grid}


def bomber_state(model,initial,t):
    grid=initial.copy()
    pos=model['start']
    last=None
    for e in model['events']:
        if t<e['start']:break
        last=e
        if t<e['plant']:
            pos=walk_pos(e['route'],t-e['start'],.075)
        elif t<e['escape_start']:
            pos=e['route'][-1]
        else:
            pos=walk_pos(e['retreat'],t-e['escape_start'],.075)
        if t>=e['explosion']:
            for p in e['hits']:grid[p]-=1
    return grid,pos,last


def plan_miners(initial,seed):
    rng=random.Random(seed)
    grid=initial.copy()
    xs=[p[0] for p,v in grid.items() if v]
    sx=max(-1,min(xs,default=44)-2)
    bots=[{'p':(sx,-1),'mode':'idle','route':[], 'target':None,'start':0.},
          {'p':(sx,7),'mode':'idle','route':[], 'target':None,'start':0.}]
    states=[]; events=[]; audit=[]
    dt=1/FPS
    for frame in range(round(DURATION*FPS)):
        t=frame*dt
        for i,b in enumerate(bots):
            if t<1.8 or t>16:continue
            if b['mode']=='idle':
                parents=bfs(b['p'],grid)
                reserved={a['target'] for j,a in enumerate(bots) if j!=i and a['target']}
                choices=[]
                for target,hp in grid.items():
                    if hp<=0 or target in reserved:continue
                    for dx,dy in DIRS:
                        stand=(target[0]+dx,target[1]+dy)
                        if stand not in parents:continue
                        route=path_to(parents,stand)
                        score=(len(route)-1)*.095+.12*hp+rng.random()*.23
                        choices.append((score,target,route))
                if choices:
                    _,target,route=min(choices,key=lambda v:v[0])
                    audit.append((grid.copy(),route,target))
                    b.update(mode='walk',target=target,route=route,start=t)
            elif b['mode']=='walk':
                if t-b['start']>=(len(b['route'])-1)*.095:
                    b.update(mode='mine',p=b['route'][-1],start=t)
            elif b['mode']=='mine':
                p=b['target']
                duration=.16+.12*initial[p]
                if t-b['start']>=duration:
                    events.append({'t':t,'p':p,'level':grid[p],'bot':i})
                    grid[p]=0
                    b.update(mode='idle',target=None,start=t)
        shown=[]
        for i,b in enumerate(bots):
            p=walk_pos(b['route'],t-b['start'],.095) if b['mode']=='walk' else b['p']
            prog=0 if b['mode']!='mine' else min(1,(t-b['start'])/(.16+.12*initial[b['target']]))
            shown.append({'p':p,'mode':b['mode'],'target':b['target'],'progress':prog,'id':i})
        states.append({'t':t,'grid':grid.copy(),'bots':shown,'cleared':len(events)})
    return {'states':states,'events':events,'audit':audit,'final':grid}


def plan_defense(initial,seed):
    rng=random.Random(seed)
    active=[p for p,v in initial.items() if v]
    sx=max(-1,min((p[0] for p in active),default=44)-5)
    start=(sx,3)
    if initial.get(start,0):start=(sx,7)
    parents=bfs(start,initial)
    route=path_to(parents,(COLS,5))
    if not route:route=path_to(parents,(COLS,7))
    if not route:raise ValueError('No path across the heatmap')
    towers=[{'p':p,'level':v,'next':0.} for p,v in initial.items() if v>=2]
    creeps=[]
    for wave,(begin,n) in enumerate([(1.8,6),(6.3,8),(10.8,10)]):
        for i in range(n):
            hp=22+wave*6+(i%3)*6
            creeps.append({'id':len(creeps),'born':begin+i*.26,'hp':float(hp),'maxhp':hp,
                           'speed':4.7+rng.random()*.9,'state':'waiting','progress':0.,'p':route[0],
                           'wave':wave+1})
    bullets=[]; shots=[]; deaths=[]; states=[]; escaped=0
    for fi in range(round(DURATION*FPS)):
        t=fi/FPS
        for e in creeps:
            if e['state']=='waiting' and t>=e['born']:e['state']='alive'
            if e['state']=='alive':
                e['progress']=(t-e['born'])*e['speed']
                e['p']=walk_pos(route,t-e['born'],1/e['speed'])
                if e['progress']>=len(route)-1:
                    e['state']='escaped';escaped+=1
        for bullet in bullets[:]:
            e=creeps[bullet['target']]
            if t>=bullet['end']:
                if e['state']=='alive':
                    e['hp']-=bullet['damage']
                    if e['hp']<=0:
                        e['state']='dead';deaths.append({'t':t,'p':e['p'],'id':e['id']})
                bullets.remove(bullet)
        for tower in towers:
            if t<tower['next']:continue
            radius=3.1+.3*tower['level']
            candidates=[e for e in creeps if e['state']=='alive' and math.dist(e['p'],tower['p'])<=radius]
            if candidates:
                target=max(candidates,key=lambda e:e['progress'])
                bullet={'start':t,'end':t+.18,'from':tower['p'],'target':target['id'],
                        'damage':2.4+tower['level']*.8,'level':tower['level']}
                bullets.append(bullet);shots.append(bullet.copy())
                tower['next']=t+.93-.10*tower['level']
        states.append({'t':t,'creeps':[e.copy() for e in creeps if e['state']=='alive'],
                       'bullets':[dict(b,to=creeps[b['target']]['p']) for b in bullets],
                       'kills':sum(e['state']=='dead' for e in creeps),'escaped':escaped,
                       'wave':min(3,1+int(max(0,t-1.8)/4.5))})
    return {'states':states,'route':route,'towers':towers,'deaths':deaths,'shots':shots}


def font(size,bold=False,mono=False):
    candidates=[Path('/usr/share/fonts/truetype/dejavu')/('DejaVuSansMono.ttf' if mono else ('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')),
                Path('C:/Windows/Fonts')/('consola.ttf' if mono else ('arialbd.ttf' if bold else 'arial.ttf'))]
    for p in candidates:
        if p.exists():return ImageFont.truetype(str(p),size)
    return ImageFont.load_default(size=size)

FONTS={k:font(*v) for k,v in {'title':(22,True),'label':(10,False,True),'small':(12,), 'body':(13,), 'hud':(13,True,True)}.items()}


class View:
    def __init__(self,t,focus,enabled=True):
        z=smooth((t-.85)/1.25)*(1-smooth((t-16.4)/1.2)) if enabled else 0
        self.z=z
        self.pitch=18*(1+(FOCUS_ZOOM-1)*z)
        self.cx=lerp((COLS-1)/2,focus,z)
        self.cy=2.9
    def xy(self,p):
        return (W/2+(p[0]-self.cx)*self.pitch,218+(p[1]-self.cy)*self.pitch)


def rect(d,box,fill,outline=None,r=0,width=1):
    box=tuple(round(v) for v in box)
    if r:d.rounded_rectangle(box,radius=round(r),fill=fill,outline=outline,width=width)
    else:d.rectangle(box,fill=fill,outline=outline,width=width)


def text(d,p,s,style='small',fill=None,anchor=None):
    d.text(p,s,font=FONTS[style],fill=TEXT if fill is None else fill,anchor=anchor)


def base(initial,grid,missing,scene,t,focus,cleared=0):
    img=Image.new('RGB',(W,H),BG);d=ImageDraw.Draw(img)
    num,title,subtitle,accent=SCENES[scene]
    text(d,(28,18),f'{OWNER}  /  {num}',style='label',fill=accent)
    text(d,(28,37),title,style='title')
    text(d,(28,69),subtitle,fill=MUTED)
    # A fixed whole-year minimap remains visible while the camera zooms.
    mx,my,mp=716,24,290/COLS
    for p,v in initial.items():
        if p in missing:continue
        x,y=mx+p[0]*mp,my+p[1]*mp
        rect(d,(x,y,x+3.7,y+3.7),GREEN[v])
    active=[p[0] for p,v in initial.items() if v]
    if active:
        x=mx+(min(active)-.6)*mp
        rect(d,(x,my-3,mx+(max(active)+1.5)*mp,my+ROWS*mp+1),None,accent,r=3)
    text(d,(1013,69),f'{COLS} WEEKS / {DATA_LABEL}',style='label',fill=MUTED,anchor='ra')
    d.line((28,95,W-28,95),fill=LINE)
    v=View(t,focus)
    if not any(initial.values()):
        text(d,(W/2,340),'NO ACTIVE DAYS IN THIS SNAPSHOT - NOTHING INVENTED',fill=MUTED,anchor='mm')
    for p,level in grid.items():
        if p in missing:continue
        x,y=v.xy(p);size=v.pitch*.74
        if x<-20 or x>W+20:continue
        color=GREEN[level]
        rect(d,(x-size/2,y-size/2,x+size/2,y+size/2),color,r=v.pitch*.10)
        if initial[p] and not level:
            rect(d,(x-size/2,y-size/2,x+size/2,y+size/2),None,'#243329',r=v.pitch*.1)
        elif level and level<initial[p]:
            d.line((x-size*.3,y-size*.3,x+size*.14,y,x-size*.14,y+size*.31),fill='#a8dfb0',width=1)
    d.line((28,370,W-28,370),fill=LINE)
    # Footer is always outside the animation area.
    img._arcade_header = img.crop((0,0,W,98))
    img._arcade_rule = img.crop((0,370,W,383))
    return img,d,v


def finish_frame(img):
    img.paste(img._arcade_header,(0,0))
    img.paste(img._arcade_rule,(0,370))
    return img


def robot(d,v,p,t,color=CYAN,facing=(1,0),drill=False):
    x,y=v.xy(p);s=v.pitch/18
    # Pixel-like robot silhouette: feet, helmet, visor, antenna.
    rect(d,(x-5*s,y+4*s,x-1*s,y+7*s),'#334350',r=s)
    rect(d,(x+1*s,y+4*s,x+5*s,y+7*s),'#334350',r=s)
    rect(d,(x-6*s,y-5*s,x+6*s,y+4*s),color,r=2*s)
    rect(d,(x-4*s,y-2*s,x+4*s,y+1*s),'#12222c',r=s)
    rect(d,(x-2*s,y-1*s,x,y),'#e6ffff')
    d.line((x,y-5*s,x,y-8*s),fill=color,width=max(1,round(s)))
    d.ellipse((x-1*s,y-9*s,x+1*s,y-7*s),fill=GOLD)
    if drill:
        fx,fy=facing
        n=math.hypot(fx,fy) or 1
        fx/=n;fy/=n
        d.line((x+fx*5*s,y+fy*5*s,x+fx*12*s,y+fy*12*s),fill='#dee8ed',width=max(2,round(3*s)))
        px,py=x+fx*13*s,y+fy*13*s
        a=t*28
        for k in range(3):
            ang=a+k*math.tau/3
            d.line((px,py,px+math.cos(ang)*4*s,py+math.sin(ang)*4*s),fill=GOLD,width=max(1,round(s)))


def burst(d,v,p,age,color,seed=0,life=.55):
    if not 0<=age<life:return
    x,y=v.xy(p);rng=random.Random(seed)
    for k in range(8):
        angle=rng.random()*math.tau;speed=12+rng.random()*24
        length=(age/life)*speed*v.pitch/18
        px=x+math.cos(angle)*length;py=y+math.sin(angle)*length+age*age*30
        sz=max(1,(1-age/life)*3*v.pitch/18)
        rect(d,(px-sz/2,py-sz/2,px+sz/2,py+sz/2),color)


def draw_bomber(model,initial,missing,t,focus):
    grid,pos,current=bomber_state(model,initial,t)
    img,d,v=base(initial,grid,missing,'bomber',t,focus)
    alive=sum(x>0 for x in grid.values());total=sum(x>0 for x in initial.values())
    # Show the genuine blast geometry. A ray stops at its first wall.
    for j,e in enumerate(model['events']):
        if e['plant']<=t<e['explosion']:
            p=e['route'][-1];x,y=v.xy(p);s=v.pitch/18
            r=(4.6+.4*math.sin(t*20))*s
            d.ellipse((x-r,y-r,x+r,y+r),fill='#303b49',outline=GOLD,width=max(1,round(s)))
            d.line((x,y-r,x+3*s,y-r-3*s),fill=GOLD,width=max(1,round(s)))
            d.ellipse((x+2*s,y-r-5*s,x+5*s,y-r-2*s),fill='#fff3b0')
            if e['explosion']-t<.23:
                for bp in e['cells']:
                    px,py=v.xy(bp);sz=v.pitch*.79
                    rect(d,(px-sz/2,py-sz/2,px+sz/2,py+sz/2),None,'#75602f',r=3)
        a=t-e['explosion']
        if 0<=a<.38:
            for bp in e['cells']:
                x,y=v.xy(bp);sz=v.pitch*(.73+.18*math.sin(a/.38*math.pi))
                color=GOLD if a<.19 else '#c87137'
                rect(d,(x-sz/2,y-sz/2,x+sz/2,y+sz/2),color,r=sz*.18)
                rect(d,(x-sz*.17,y-sz*.17,x+sz*.17,y+sz*.17),'#fff6c3',r=2)
        for p in e['hits']:burst(d,v,p,a,GOLD,j*97+p[0]*7+p[1])
    robot(d,v,pos,t,color=TEXT)
    planted=sum(t>=e['plant'] for e in model['events'])
    rect(d,(0,383,W,H),BG)
    text(d,(28,389),'WALK > PLANT > ESCAPE > BOOM',style='label',fill=GOLD)
    text(d,(1012,389),f'BOMBS {planted:02d}   /   WALLS CLEARED {total-alive:02d}/{total:02d}',style='hud',anchor='ra')
    return finish_frame(img)


def draw_miners(model,initial,missing,t,focus):
    st=model['states'][min(len(model['states'])-1,round(t*FPS))]
    img,d,v=base(initial,st['grid'],missing,'miners',t,focus)
    # Track in the explicit aisle below the calendar, never replacing a day.
    lx,ly=v.xy((focus-5,7.4));rx,_=v.xy((focus+5,7.4))
    d.line((lx,ly,rx,ly),fill='#303d48',width=2)
    for q in range(11):
        x,y=v.xy((focus-5+q,7.4));d.line((x,y-3,x,y+3),fill='#303d48')
    cartx=focus-1+3*math.sin(t*.6);x,y=v.xy((cartx,7.2));s=v.pitch/18
    rect(d,(x-9*s,y-5*s,x+9*s,y+3*s),'#394b59',r=2*s)
    rect(d,(x-7*s,y-4*s,x+7*s,y-1*s),'#e9b95b',r=s)
    for off in [-5,5]:d.ellipse((x+(off-2)*s,y+2*s,x+(off+2)*s,y+6*s),fill='#6e8597')
    for b in st['bots']:
        color=CYAN if b['id']==0 else GOLD
        if b['mode']=='mine':
            target=b['target'];tx,ty=v.xy(target);sz=v.pitch*.74
            progress=b['progress']
            d.line((tx-sz*.3,ty-sz*.4,tx+sz*.18,ty,tx-sz*.13,ty+sz*.4),fill='#d3fada',width=max(1,round(progress*2)))
            rect(d,(tx-sz/2,ty+sz/2+3,tx+sz/2,ty+sz/2+5),'#243640')
            rect(d,(tx-sz/2,ty+sz/2+3,tx-sz/2+sz*progress,ty+sz/2+5),color)
            if int(t*24)%2:
                burst(d,v,target,.12,color,int(t*5)+b['id'])
            robot(d,v,b['p'],t,color,(target[0]-b['p'][0],target[1]-b['p'][1]),True)
        else:robot(d,v,b['p'],t,color)
    for e in model['events']:
        age=t-e['t'];color=CYAN if e['bot']==0 else GOLD
        if 0<=age<.85:
            burst(d,v,e['p'],age,GREEN[min(4,e['level'])],int(e['t']*100))
            f=smooth(age/.85)
            start=v.xy(e['p']);dest=v.xy((cartx,7.05))
            px=lerp(start[0],dest[0],f);py=lerp(start[1],dest[1],f)-math.sin(f*math.pi)*32
            rect(d,(px-3,py-3,px+3,py+3),color,r=1)
    total=sum(v>0 for v in initial.values())
    rect(d,(0,383,W,H),BG)
    text(d,(28,389),'REAL ROUTES   /   HIGHER INTENSITY = HARDER ORE',style='label',fill=CYAN)
    text(d,(1012,389),f'CREW 02   /   CELLS MINED {st["cleared"]:02d}/{total:02d}',style='hud',anchor='ra')
    return finish_frame(img)


def bug(d,v,p,t,health,maxhealth,identity):
    x,y=v.xy(p);s=v.pitch/18
    for i in [-1,1]:
        for j in [-1,1]:
            dx=math.sin(t*24+identity)*s
            d.line((x+i*3*s,y+j*2*s,x+i*7*s,y+j*4*s+dx),fill='#eb9273',width=max(1,round(s)))
    d.ellipse((x-4*s,y-4*s,x+4*s,y+4*s),fill=RED)
    d.line((x,y-3*s,x,y+3*s),fill='#773d3a',width=max(1,round(s)))
    if health<maxhealth:
        rect(d,(x-5*s,y-7*s,x+5*s,y-6*s),'#472c2b')
        rect(d,(x-5*s,y-7*s,x-5*s+10*s*max(0,health/maxhealth),y-6*s),GOLD)


def draw_defense(model,initial,missing,t,focus):
    st=model['states'][min(len(model['states'])-1,round(t*FPS))]
    img,d,v=base(initial,initial,missing,'defense',t,focus)
    # The enemy route follows zero-contribution cells, plus the outer aisle.
    for a,b in zip(model['route'],model['route'][1:]):
        ax,ay=v.xy(a);bx,by=v.xy(b)
        d.line((ax,ay,lerp(ax,bx,.35),lerp(ay,by,.35)),fill='#2d3a47',width=1)
    for tower in model['towers']:
        p=tower['p'];level=tower['level'];x,y=v.xy(p);s=v.pitch/18
        recent=[b for b in st['bullets'] if b['from']==p]
        target=recent[-1]['to'] if recent else (p[0]-1,p[1]+1)
        vx,vy=target[0]-p[0],target[1]-p[1];length=math.hypot(vx,vy) or 1
        d.ellipse((x-4*s,y-4*s,x+4*s,y+4*s),fill='#1e3c35',outline='#abf1bb',width=max(1,round(s)))
        d.line((x,y,x+vx/length*7*s,y+vy/length*7*s),fill='#dcffe4',width=max(2,round(2*s)))
        if recent:d.ellipse((x-2*s,y-2*s,x+2*s,y+2*s),fill='#efffd2')
    for e in st['creeps']:bug(d,v,e['p'],t,e['hp'],e['maxhp'],e['id'])
    for b in st['bullets']:
        f=min(1,(t-b['start'])/(b['end']-b['start']))
        a=v.xy(b['from']);z=v.xy(b['to'])
        px=lerp(a[0],z[0],f);py=lerp(a[1],z[1],f)
        tx=lerp(a[0],z[0],max(0,f-.13));ty=lerp(a[1],z[1],max(0,f-.13))
        d.line((tx,ty,px,py),fill='#72e8b0',width=2)
        d.ellipse((px-2,py-2,px+2,py+2),fill='#e6ff9b')
    for e in model['deaths']:burst(d,v,e['p'],t-e['t'],RED,e['id']*33)
    rect(d,(0,383,W,H),BG)
    text(d,(28,389),'GREEN DAYS DEFEND   /   EMPTY DAYS LET BUGS THROUGH',style='label',fill='#b9a2ff')
    text(d,(1012,389),f'WAVE {st["wave"]:02d}   /   STOPPED {st["kills"]:02d}   /   LEAKED {st["escaped"]:02d}',style='hud',anchor='ra')
    return finish_frame(img)


PLANNERS={'bomber':plan_bomber,'miners':plan_miners,'defense':plan_defense}
DRAWERS={'bomber':draw_bomber,'miners':draw_miners,'defense':draw_defense}


def render(scene,initial,missing,seed,output,duration=DURATION,theme='dark',model=None):
    global FOCUS_ZOOM
    configure_theme(theme)
    if model is None: model=PLANNERS[scene](initial,seed)
    active=[p[0] for p,v in initial.items() if v]
    focus=(min(active)+max(active))/2 if active else 26
    FOCUS_ZOOM=max(1.,min(1.85,51/(max(active)-min(active)+7))) if active else 1.
    frames=[]
    # One palette for the entire GIF prevents inter-frame colour flicker.
    samples=[DRAWERS[scene](model,initial,missing,t,focus) for t in [0,3,5,8,11,14]]
    strip=Image.new('RGB',(W,H*len(samples)))
    for j,s in enumerate(samples):strip.paste(s,(0,j*H))
    palette=strip.quantize(colors=192,method=Image.Quantize.MEDIANCUT)
    del strip,samples
    for f in range(round(duration*FPS)):
        frame=DRAWERS[scene](model,initial,missing,f/FPS,focus)
        frames.append(frame.quantize(palette=palette,dither=Image.Dither.NONE))
    output.parent.mkdir(parents=True,exist_ok=True)
    offset=round((6.1 if scene=='bomber' else 5.8 if scene=='miners' else 10.3)*FPS)
    frames=frames[offset:]+frames[:offset]
    frames[0].save(output,save_all=True,append_images=frames[1:],duration=round(1000/FPS),loop=0,optimize=True,disposal=1)
    still=DRAWERS[scene](model,initial,missing,8.2,focus)
    still.save(output.with_suffix('.png'))
    metrics={'scene':scene,'theme':theme,'frames':len(frames),'seconds':duration,'seed':seed,'active_cells':sum(v>0 for v in initial.values()),'file_bytes':output.stat().st_size}
    if scene=='bomber':metrics['bombs']=len(model['events']);metrics['cleared']=sum(initial[p]>0 and not v for p,v in model['final'].items())
    if scene=='miners':metrics['cleared']=len(model['events'])
    if scene=='defense':metrics.update({k:model['states'][-1][k] for k in ['kills','escaped']})
    if scene in ('pinball','laser','gravity'):metrics['events']=len(model['events'])
    output.with_suffix('.metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
    print(json.dumps(metrics),flush=True)
    return model


def configure_theme(theme):
    """Theme changes affect the renderer, never the simulation."""
    global BG, TEXT, MUTED, LINE, GREEN
    if theme not in ('dark', 'light'):
        raise ValueError('Unknown theme')
    BG, TEXT, MUTED, LINE = (('#0d1117','#e6edf3','#8b949e','#26323f') if theme == 'dark'
                            else ('#ffffff','#1f2328','#59636e','#d1d9e0'))
    GREEN = (['#161b22','#0e4429','#006d32','#26a641','#39d353'] if theme == 'dark'
             else ['#eff2f5','#9be9a8','#40c463','#30a14e','#216e39'])
