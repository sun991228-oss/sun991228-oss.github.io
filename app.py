"""
근무성적 평정 시스템 v3
조직구조: 3부 9팀 / 직책: 대표이사·본부장·부장·팀장·팀원 / 직급: 2~6급
평가체계: 1차(팀장→팀원) / 2차(부장→소속부전체) / 3차(본부장→전직원) / 4차(대표이사→전직원)
"""

import streamlit as st
import json, hashlib, io, re
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import pandas as pd

# ══════════════════════════════════════════════
# 상수 & 조직 구조
# ══════════════════════════════════════════════
ORG = {
    "경영지원부":     ["행정지원팀", "재정관리팀", "생산관리팀"],
    "직매장사업부":   ["도담점", "아름점", "새롬점", "소담점", "직매장행정팀"],
    "공공급식사업부": ["공공급식팀"],
}
ALL_DEPTS = list(ORG.keys())
ALL_TEAMS = [t for teams in ORG.values() for t in teams]
POSITIONS = ["대표이사", "본부장", "부장", "팀장", "팀원"]
GRADES    = ["2급", "3급", "4급", "5급", "6급"]

EVAL_WEIGHTS = {"1차": 0.3, "2차": 0.3, "3차": 0.2, "4차": 0.2}

DEDUCTION_RATES = {
    "지각":           ("회",  0.15),
    "무단결근":       ("일",  0.50),
    "무단조퇴":       ("회",  0.25),
    "무단외출(이석)": ("회",  0.25),
    "민원야기":       ("건",  0.50),
    "경고(훈계·주의)":("건",  0.50),
    "정직":           ("건",  2.50),
    "직위해제":       ("건",  2.50),
    "감봉":           ("건",  2.00),
    "견책":           ("건",  1.50),
    "불문경고":       ("건",  1.00),
}

ABILITY_ITEMS = [
    ("직무능력", 7, ". 업무수행 단계별 일정 준수 및 보고\n. 업무수행 결과의 효과성 및 업무 완결도"),
    ("관계능력", 7, ". 회사내에서의 동료의식 및 태도\n. 유관기관, 고객, 거래처 등과 원활한 조정 및 관리"),
    ("팔로우십", 7, ". 팀장의 업무추진에 대한 지원의 적극성\n. 팀워크 활성화를 위한 기여도"),
    ("창의력",   7, ". 기존 사업에 대한 창의적 기획\n. 새로운 사업 발굴 및 만족도 제고"),
    ("소통능력", 7, ". 문서·보고서 작성을 통한 공식적인 소통 능력\n. 다른 사람의 의견을 경청하는 능력\n. 주변의 의견을 기꺼이 받아들이고 개선하는 태도"),
]

# ══════════════════════════════════════════════
# 경로
# ══════════════════════════════════════════════
DATA_DIR    = Path("data")
UPLOADS_DIR = DATA_DIR / "uploads"
for _d in [DATA_DIR, UPLOADS_DIR]:
    _d.mkdir(exist_ok=True)

USERS_FILE       = DATA_DIR / "users.json"
EVALUATIONS_FILE = DATA_DIR / "evaluations.json"
TASKS_FILE       = DATA_DIR / "tasks.json"
PROFILES_FILE    = DATA_DIR / "profiles.json"

# ══════════════════════════════════════════════
# 유틸
# ══════════════════════════════════════════════
def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default

def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def hash_pw(pw): return hashlib.sha256(str(pw).encode()).hexdigest()

def is_valid_id(uid):
    return bool(uid) and bool(re.match(r'^[a-zA-Z0-9_]+$', str(uid)))

def get_users():       return load_json(USERS_FILE, {})
def get_evaluations(): return load_json(EVALUATIONS_FILE, {})
def get_tasks():       return load_json(TASKS_FILE, {})
def get_profiles():    return load_json(PROFILES_FILE, {})

def get_evaluatees():
    return {k: v for k, v in get_users().items() if v.get("role") == "evaluatee"}

def pdf_path(uid): return UPLOADS_DIR / f"{uid}.pdf"

def get_team_dept(team):
    for dept, teams in ORG.items():
        if team in teams:
            return dept
    return ""

def grade_label(s):
    if s >= 90: return "S"
    if s >= 80: return "A"
    if s >= 70: return "B"
    if s >= 60: return "C"
    return "D"

def score_color(s):
    if s >= 80: return "#2ecc71"
    if s >= 60: return "#e67e22"
    return "#e74c3c"

# ══════════════════════════════════════════════
# 조직 기반 평가 범위
# ══════════════════════════════════════════════
def get_stage_for_evaluator(uid):
    pos = get_users().get(uid, {}).get("position", "")
    return {"팀장": "1차", "부장": "2차", "본부장": "3차", "대표이사": "4차"}.get(pos, "")

def get_evaluatee_scope(ev_uid):
    users    = get_users()
    profiles = get_profiles()
    ev       = users.get(ev_uid, {})
    ev_pos   = ev.get("position", "")
    ev_dept  = ev.get("dept", "")
    ev_team  = ev.get("team", "")
    result   = []

    for uid, u in users.items():
        if u.get("role") != "evaluatee":
            continue
        p       = profiles.get(uid, {})
        ee_team = p.get("team", u.get("team", ""))
        ee_dept = get_team_dept(ee_team)
        ee_pos  = p.get("position", u.get("position", "팀원"))

        if ev_pos == "팀장"    and ee_team == ev_team:                        result.append(uid)
        elif ev_pos == "부장"  and ee_dept == ev_dept:                        result.append(uid)
        elif ev_pos == "본부장" and ee_pos in ("팀원","팀장","부장"):         result.append(uid)
        elif ev_pos == "대표이사":                                             result.append(uid)

    return result

# ══════════════════════════════════════════════
# 점수 계산
# ══════════════════════════════════════════════
def calc_task_score(tasks, ev_stage_data):
    return round(sum(ev_stage_data.get("tasks", {}).get(t["id"], 0) * t["weight"] * 6
                     for t in tasks), 2)

def calc_ability_score(ev_stage_data):
    ab = ev_stage_data.get("ability", {})
    return round(sum(ab.get(n, 0) for n, _, _ in ABILITY_ITEMS), 2)

def calc_attitude_score(deductions):
    total = sum(deductions.get(item, 0) * rate for item, (_, rate) in DEDUCTION_RATES.items())
    return round(max(0.0, 5.0 - total), 2)

def calc_final(ee_id, evaluations, tasks_data):
    tasks      = tasks_data.get(ee_id, {}).get("tasks", [])
    deductions = evaluations.get(ee_id, {}).get("deductions", {})
    att_c      = calc_attitude_score(deductions)
    result     = {}
    w_a = w_b = w_ab = 0.0
    all_done   = True

    for stage, weight in EVAL_WEIGHTS.items():
        ev_data = evaluations.get(ee_id, {}).get(stage, {})
        if not ev_data:
            all_done = False
            continue
        a = calc_task_score(tasks, ev_data)
        b = calc_ability_score(ev_data)
        result[stage] = {"A": a, "B": b, "AB": round(a+b,2), "weight": weight}
        w_a  += a * weight
        w_b  += b * weight
        w_ab += (a+b) * weight

    ded_done = evaluations.get(ee_id, {}).get("deductions") is not None
    result["종합"] = {
        "A_가중":  round(w_a,2),  "B_가중": round(w_b,2),
        "AB_가중": round(w_ab,2), "C": att_c,
        "최종":    round(w_ab + att_c, 2),
        "완료":    all_done and ded_done,
    }
    return result

def calc_grade_rankings(evaluations, tasks_data):
    users    = get_users()
    profiles = get_profiles()
    rows = []
    for uid, u in users.items():
        if u.get("role") != "evaluatee":
            continue
        p      = profiles.get(uid, {})
        result = calc_final(uid, evaluations, tasks_data)
        종합   = result.get("종합", {})
        if not 종합.get("완료"):
            continue
        rows.append({
            "uid":       uid,
            "이름":      u.get("name",""),
            "소속부":    get_team_dept(p.get("team", u.get("team",""))),
            "소속팀":    p.get("team", u.get("team","")),
            "직책":      p.get("position", u.get("position","")),
            "직급":      p.get("grade", u.get("grade","")),
            "최종점수":  종합["최종"],
            "근무실적(A)": 종합["A_가중"],
            "직무능력(B)": 종합["B_가중"],
            "직무태도(C)": 종합["C"],
            **{f"{st} 환산": result.get(st, {}).get("AB", "-") for st in EVAL_WEIGHTS},
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["직급순위"] = df.groupby("직급")["최종점수"].rank(method="min", ascending=False).astype(int)
    return df.sort_values(["직급", "직급순위"]).reset_index(drop=True)

# ══════════════════════════════════════════════
# 초기화
# ══════════════════════════════════════════════
def init_defaults():
    if not USERS_FILE.exists():
        save_json(USERS_FILE, {"admin": {"password": hash_pw("admin"), "role": "admin", "name": "인사팀 총괄"}})
    for f, d in [(EVALUATIONS_FILE,{}),(TASKS_FILE,{}),(PROFILES_FILE,{})]:
        if not f.exists(): save_json(f, d)

init_defaults()

for _k, _v in [("logged_in",False),("username",""),("role",""),("name","")]:
    if _k not in st.session_state: st.session_state[_k] = _v

# ══════════════════════════════════════════════════════════════
# 로그인
# ══════════════════════════════════════════════════════════════
def show_login():
    st.markdown("""
    <div style='text-align:center;padding:2.5rem 0 1rem'>
      <h1 style='font-size:2.2rem;color:#1F4E79'>📋 근무성적 평정 시스템</h1>
      <p style='color:#888'>계정 유형에 맞게 로그인하세요</p>
    </div>""", unsafe_allow_html=True)
    _, col, _ = st.columns([1,2,1])
    with col:
        with st.container(border=True):
            st.subheader("🔐 로그인")
            uid = st.text_input("아이디")
            pw  = st.text_input("비밀번호", type="password")
            if st.button("로그인", type="primary", use_container_width=True):
                users = get_users()
                if uid in users and users[uid]["password"] == hash_pw(pw):
                    for k,v in [("logged_in",True),("username",uid),
                                 ("role",users[uid]["role"]),("name",users[uid]["name"])]:
                        st.session_state[k] = v
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호가 올바르지 않습니다.")

# ══════════════════════════════════════════════════════════════
# 피평가자
# ══════════════════════════════════════════════════════════════
def show_evaluatee():
    uid      = st.session_state.username
    name     = st.session_state.name
    u        = get_users().get(uid, {})
    profiles = get_profiles()
    p        = profiles.get(uid, {})
    team     = p.get("team", u.get("team",""))
    dept     = get_team_dept(team)
    pos      = p.get("position", u.get("position",""))
    grd      = p.get("grade", u.get("grade",""))

    st.title("📄 내 근무성적 평정")
    st.caption(f"👤 {name} | {dept} {team} | {pos} ({grd})")
    st.divider()

    t1, t2, t3, t4 = st.tabs(["👤 인적사항","📝 담당업무·과제","📁 성과보고서","📊 평가 결과"])

    with t1:
        st.subheader("인적 사항")
        st.info(f"소속: **{dept} / {team}** | 직책: **{pos}** | 직급: **{grd}**\n\n*(조직 정보는 총괄 관리자가 관리합니다)*")
        with st.form("profile_form"):
            c1, c2 = st.columns(2)
            ipsa     = c1.text_input("입사일",       value=p.get("입사일",""),       placeholder="예: 2020-03-02")
            hyun_jik = c1.text_input("현직급임용일", value=p.get("현직급임용일",""), placeholder="예: 2023-01-01")
            hyun_bo  = c1.text_input("현보직일",     value=p.get("현보직일",""),     placeholder="예: 2024-03-01")
            damdan   = c2.text_input("담당업무(요약)",value=p.get("담당업무",""))
            if st.form_submit_button("💾 저장", type="primary"):
                profiles[uid] = {**p, "입사일":ipsa,"현직급임용일":hyun_jik,"현보직일":hyun_bo,"담당업무":damdan}
                save_json(PROFILES_FILE, profiles)
                st.success("저장되었습니다.")

    with t2:
        st.subheader("담당업무·과제 등록")
        st.caption("개별과제(최대 5개) + 팀별과제(1개) / 업무비중 합계 = 1.00")
        tasks_data = get_tasks()
        my_tasks   = tasks_data.get(uid, {}).get("tasks", [])
        with st.form("task_form"):
            st.markdown("**개별과제**")
            indiv_prev = [t for t in my_tasks if t.get("type")=="개별"]
            team_prev  = next((t for t in my_tasks if t.get("type")=="팀별"), {})
            indiv_new  = []
            for i in range(5):
                pr = indiv_prev[i] if i < len(indiv_prev) else {}
                c1, c2, c3 = st.columns([3,1,4])
                title  = c1.text_input(f"과제명 {i+1}", value=pr.get("title",""), key=f"it{i}")
                weight = c2.number_input("비중", 0.0, 1.0, float(pr.get("weight",0.0)), 0.05,
                                         format="%.2f", key=f"iw{i}")
                res    = c3.text_area("주요실적", value=pr.get("result",""), height=60, key=f"ir{i}")
                if title:
                    indiv_new.append({"id":f"indiv_{i}","type":"개별","no":i+1,
                                      "title":title,"weight":weight,"result":res})
            st.markdown("**팀별과제**")
            c1, c2, c3 = st.columns([3,1,4])
            t_title  = c1.text_input("팀별과제명", value=team_prev.get("title",""))
            t_weight = c2.number_input("비중", 0.0, 1.0, float(team_prev.get("weight",0.1)),
                                        0.05, format="%.2f", key="tw")
            t_res    = c3.text_area("주요실적", value=team_prev.get("result",""), height=60)
            team_new = [{"id":"team_0","type":"팀별","no":1,
                         "title":t_title,"weight":t_weight,"result":t_res}] if t_title else []
            all_tasks = indiv_new + team_new
            total_w   = round(sum(t["weight"] for t in all_tasks), 2)
            delta_str = "✅ 정상" if abs(total_w-1.0)<0.001 else f"{total_w-1:.2f} (오류)"
            st.metric("업무비중 합계", f"{total_w:.2f}", delta=delta_str)
            if st.form_submit_button("💾 과제 저장", type="primary"):
                if abs(total_w-1.0) > 0.001:
                    st.error(f"업무비중 합계가 1.00이어야 합니다. (현재 {total_w:.2f})")
                elif not all_tasks:
                    st.error("과제를 최소 1개 입력하세요.")
                else:
                    tasks_data[uid] = {"tasks":all_tasks,"updated":datetime.now().strftime("%Y-%m-%d %H:%M")}
                    save_json(TASKS_FILE, tasks_data)
                    st.success("저장되었습니다."); st.rerun()
        if my_tasks:
            st.divider()
            st.dataframe(pd.DataFrame([{"구분":t["type"],"번호":t["no"],"과제명":t["title"],
                                         "비중":f"{t['weight']:.0%}","주요실적":t.get("result","")}
                                        for t in my_tasks]), use_container_width=True, hide_index=True)

    with t3:
        st.subheader("성과보고서 PDF 업로드")
        pp = pdf_path(uid)
        c1, c2 = st.columns(2)
        with c1:
            with st.container(border=True):
                if pp.exists():
                    stat = pp.stat()
                    st.success("✅ 업로드 완료")
                    st.markdown(f"- 크기: {stat.st_size/1024:.1f} KB")
                    st.markdown(f"- 일시: {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')}")
                    with open(pp,"rb") as f:
                        st.download_button("⬇️ 내 보고서 다운로드", data=f,
                                           file_name=f"{name}_성과보고서.pdf",
                                           mime="application/pdf", use_container_width=True)
                else:
                    st.warning("아직 업로드하지 않았습니다.")
        with c2:
            with st.container(border=True):
                up = st.file_uploader("PDF 선택", type=["pdf"], label_visibility="collapsed")
                if up and st.button("업로드 확정", type="primary", use_container_width=True):
                    pp.write_bytes(up.read()); st.success("업로드 완료!"); st.rerun()

    with t4:
        st.subheader("내 평가 결과")
        evaluations = get_evaluations()
        tasks_data  = get_tasks()
        result = calc_final(uid, evaluations, tasks_data)
        종합   = result.get("종합", {})
        if not any(s in result for s in EVAL_WEIGHTS):
            st.info("아직 평가 결과가 없습니다.")
        else:
            cols = st.columns(4)
            for i, (stage, weight) in enumerate(EVAL_WEIGHTS.items()):
                with cols[i]:
                    with st.container(border=True):
                        st.markdown(f"**{stage}** ({int(weight*100)}%)")
                        if stage in result:
                            r = result[stage]
                            st.metric("근무실적 A", f"{r['A']:.1f}점")
                            st.metric("직무능력 B", f"{r['B']:.1f}점")
                            st.metric("소계 A+B",   f"{r['AB']:.1f}점")
                        else:
                            st.caption("평가 대기")
            st.divider()
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("가중 A", f"{종합.get('A_가중',0):.1f}점")
            c2.metric("가중 B", f"{종합.get('B_가중',0):.1f}점")
            c3.metric("태도 C", f"{종합.get('C',5):.1f}점")
            final = 종합.get("최종",0)
            color = score_color(final)
            c4.markdown(
                f"<div style='text-align:center;padding:.6rem;border-radius:8px;"
                f"background:{color}20;border:2px solid {color}'>"
                f"<div style='font-size:.75rem;color:#555'>최종 합계</div>"
                f"<div style='font-size:2rem;font-weight:bold;color:{color}'>{final:.1f}점</div>"
                f"<div style='color:{color}'>{grade_label(final)}등급</div></div>",
                unsafe_allow_html=True)
            for stage in EVAL_WEIGHTS:
                op = evaluations.get(uid,{}).get(stage,{}).get("opinion","")
                if op: st.markdown(f"**{stage} 평정 의견:** {op}")

# ══════════════════════════════════════════════════════════════
# 평가자
# ══════════════════════════════════════════════════════════════
def show_evaluator():
    ev_uid  = st.session_state.username
    ev_name = st.session_state.name
    users   = get_users()
    ev_pos  = users.get(ev_uid, {}).get("position", "")
    stage   = get_stage_for_evaluator(ev_uid)

    st.title(f"✍️ {stage} 평가")
    st.caption(f"👤 {ev_name} | 직책: {ev_pos} | 담당 차수: {stage}")
    st.divider()

    tasks_data  = get_tasks()
    evaluations = get_evaluations()
    profiles    = get_profiles()
    assigned    = get_evaluatee_scope(ev_uid)

    if not assigned:
        st.warning("담당 피평가자가 없습니다. 총괄 관리자에게 문의하세요."); return

    stage_order = list(EVAL_WEIGHTS.keys())
    prev_stage  = stage_order[stage_order.index(stage)-1] if stage != "1차" else None

    # 팀별 그룹핑
    group = defaultdict(list)
    for ee_id in assigned:
        ee_u = users.get(ee_id, {})
        ee_p = profiles.get(ee_id, {})
        team = ee_p.get("team", ee_u.get("team","기타"))
        group[team].append(ee_id)

    tab_names = list(group.keys())
    tabs = st.tabs(tab_names) if tab_names else []

    for tab, team_name in zip(tabs, tab_names):
        with tab:
            for ee_id in group[team_name]:
                if ee_id not in users: continue
                ee_u    = users[ee_id]
                ee_p    = profiles.get(ee_id, {})
                ee_name = ee_u.get("name", ee_id)
                ee_pos  = ee_p.get("position", ee_u.get("position",""))
                ee_grd  = ee_p.get("grade", ee_u.get("grade",""))
                tasks   = tasks_data.get(ee_id, {}).get("tasks", [])
                ev_all  = evaluations.get(ee_id, {})
                my_ev   = ev_all.get(stage, {})

                with st.expander(f"👤 {ee_name}  ({ee_pos} / {ee_grd})", expanded=False):
                    if prev_stage and not ev_all.get(prev_stage):
                        st.warning(f"⏳ {prev_stage} 평가가 완료되지 않았습니다."); continue

                    # ── 이전 차수 평가 결과 확인 ──────────────────
                    prev_stages_done = [s for s in list(EVAL_WEIGHTS.keys())
                                        if s != stage and
                                        list(EVAL_WEIGHTS.keys()).index(s) <
                                        list(EVAL_WEIGHTS.keys()).index(stage)
                                        and ev_all.get(s)]
                    if prev_stages_done:
                        with st.expander(f"📋 이전 평가 결과 보기 ({', '.join(prev_stages_done)})", expanded=False):
                            tasks = tasks_data.get(ee_id, {}).get("tasks", [])
                            p_cols = st.columns(len(prev_stages_done))
                            for col, ps in zip(p_cols, prev_stages_done):
                                ps_data = ev_all.get(ps, {})
                                a = calc_task_score(tasks, ps_data)
                                b = calc_ability_score(ps_data)
                                ev_user = users.get(ps_data.get("evaluator_id",""), {})
                                with col:
                                    st.markdown(f"**{ps} 평가결과**")
                                    st.caption(f"평가자: {ev_user.get('name', ps_data.get('evaluator_id',''))}")
                                    st.caption(f"평가일: {ps_data.get('date','')}")
                                    st.metric("근무실적 A", f"{a:.1f}점")
                                    st.metric("직무능력 B", f"{b:.1f}점")
                                    st.metric("소계 A+B",   f"{round(a+b,2):.1f}점")
                                    # 과제별 점수
                                    st.markdown("**과제별 점수**")
                                    for t in tasks:
                                        sc = ps_data.get("tasks",{}).get(t["id"],"-")
                                        conv = round(sc * t["weight"] * 6, 2) if isinstance(sc, (int,float)) else "-"
                                        st.caption(f"{'🔹' if t['type']=='개별' else '🔸'} {t['title']}: {sc}점 → {conv}점")
                                    # 직무수행능력별 점수
                                    st.markdown("**직무수행능력**")
                                    for ab_name, ab_max, _ in ABILITY_ITEMS:
                                        ab_sc = ps_data.get("ability",{}).get(ab_name,"-")
                                        st.caption(f"{ab_name}: {ab_sc}점 / {ab_max}점")
                                    # 평정 의견
                                    op = ps_data.get("opinion","")
                                    if op:
                                        st.markdown("**평정 의견**")
                                        st.info(op)
                        st.divider()

                    col_info, col_pdf = st.columns([3,1])
                    with col_info:
                        if tasks:
                            st.dataframe(pd.DataFrame([{"구분":t["type"],"과제명":t["title"],
                                                         "비중":f"{t['weight']:.0%}",
                                                         "주요실적":t.get("result","")}
                                                        for t in tasks]),
                                         use_container_width=True, hide_index=True)
                        else:
                            st.caption("등록된 과제가 없습니다.")
                    with col_pdf:
                        pp = pdf_path(ee_id)
                        if pp.exists():
                            with open(pp,"rb") as f:
                                st.download_button("⬇️ PDF 열기", data=f,
                                                   file_name=f"{ee_name}_성과보고서.pdf",
                                                   mime="application/pdf",
                                                   use_container_width=True,
                                                   key=f"pdf_{stage}_{ee_id}")
                        else:
                            st.caption("PDF 미제출")

                    with st.form(f"eval_{stage}_{ee_id}"):
                        # ① 근무실적
                        st.markdown("#### ① 근무실적 평정 (A, 60점)")
                        st.caption("과제별 10점 만점 → 환산 = 점수 × 비중 × 6")
                        task_scores = {}; task_conv = 0.0
                        if not tasks:
                            st.warning("과제가 등록되지 않았습니다.")
                        else:
                            h = st.columns([3,1,1,1])
                            h[0].markdown("**과제명**"); h[1].markdown("**비중**")
                            h[2].markdown("**평가(10점)**"); h[3].markdown("**환산**")
                            for t in tasks:
                                tid    = t["id"]
                                prev_s = my_ev.get("tasks",{}).get(tid, 10)
                                row    = st.columns([3,1,1,1])
                                row[0].markdown(f"{'🔹' if t['type']=='개별' else '🔸'} {t['title']}")
                                row[1].markdown(f"{t['weight']:.0%}")
                                sc   = row[2].number_input("", 0, 10, int(prev_s), 1,
                                                            key=f"ts_{stage}_{ee_id}_{tid}",
                                                            label_visibility="collapsed")
                                conv = round(sc * t["weight"] * 6, 2)
                                row[3].markdown(f"**{conv:.2f}**")
                                task_scores[tid] = sc; task_conv += conv
                            st.markdown(f"➡️ **근무실적 합계: {task_conv:.2f}점 / 60점**")

                        st.divider()

                        # ② 직무수행능력
                        st.markdown("#### ② 직무수행능력 (B, 35점)")
                        ability_scores = {}; ab_total = 0
                        hh = st.columns([2,1,4,1])
                        hh[0].markdown("**평정요소**"); hh[1].markdown("**배점**")
                        hh[2].markdown("**정의**");     hh[3].markdown("**점수**")
                        for ab_name, ab_max, ab_def in ABILITY_ITEMS:
                            prev_ab = my_ev.get("ability",{}).get(ab_name, ab_max)
                            row2 = st.columns([2,1,4,1])
                            row2[0].markdown(f"**{ab_name}**")
                            row2[1].markdown(f"{ab_max}점")
                            row2[2].markdown(f"<small>{ab_def.replace(chr(10),'<br>')}</small>",
                                             unsafe_allow_html=True)
                            ab_sc = row2[3].number_input("", 0, ab_max, int(prev_ab), 1,
                                                          key=f"ab_{stage}_{ee_id}_{ab_name}",
                                                          label_visibility="collapsed")
                            ability_scores[ab_name] = ab_sc; ab_total += ab_sc
                        st.markdown(f"➡️ **직무수행능력 합계: {ab_total}점 / 35점**")

                        st.divider()
                        prev_op = my_ev.get("opinion","")
                        opinion = st.text_area("📝 평정 의견", value=prev_op, height=70,
                                               placeholder="종합 의견을 작성하세요.",
                                               key=f"op_{stage}_{ee_id}")
                        submitted = st.form_submit_button("💾 평가 저장", type="primary",
                                                           use_container_width=True)

                    if submitted:
                        evaluations = get_evaluations()
                        evaluations.setdefault(ee_id, {})[stage] = {
                            "tasks": task_scores, "ability": ability_scores,
                            "opinion": opinion, "evaluator_id": ev_uid,
                            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        }
                        save_json(EVALUATIONS_FILE, evaluations)
                        st.success(f"✅ {ee_name}의 {stage} 평가 저장 완료!"); st.rerun()

                    if my_ev:
                        st.caption(f"마지막 저장: {my_ev.get('date','')} | {my_ev.get('evaluator_id','')}")

# ══════════════════════════════════════════════════════════════
# 총괄 관리자
# ══════════════════════════════════════════════════════════════
def show_admin():
    st.title("🗂️ 평가 총괄 관리")
    st.caption(f"👤 {st.session_state.name} | 총괄 관리자")
    st.divider()

    evaluations = get_evaluations()
    tasks_data  = get_tasks()
    users       = get_users()
    profiles    = get_profiles()
    evaluatees  = get_evaluatees()

    total   = len(evaluatees)
    pdf_ok  = sum(1 for u in evaluatees if pdf_path(u).exists())
    task_ok = sum(1 for u in evaluatees if tasks_data.get(u,{}).get("tasks"))
    done_4  = sum(1 for u in evaluatees if evaluations.get(u,{}).get("4차"))
    ded_ok  = sum(1 for u in evaluatees if evaluations.get(u,{}).get("deductions") is not None)
    full_ok = sum(1 for u in evaluatees
                  if calc_final(u, evaluations, tasks_data).get("종합",{}).get("완료"))

    cols = st.columns(6)
    for c, (label, val) in zip(cols, [
        ("전체 피평가자",f"{total}명"),("과제 등록",f"{task_ok}명"),
        ("PDF 제출",f"{pdf_ok}명"),("4차 완료",f"{done_4}명"),
        ("태도 입력",f"{ded_ok}명"),("전체 완료",f"{full_ok}명")
    ]):
        c.metric(label, val)

    st.divider()

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📋 전체 현황", "🧘 직무수행태도", "📊 점수 집계",
        "🏆 직급별 순위", "🧑‍💼 계정 관리", "📁 평정표 다운로드"
    ])

    # ── 탭1 전체 현황 ─────────────────────────
    with tab1:
        st.subheader("피평가자별 평가 진행 현황")
        col_fd, col_ft = st.columns(2)
        filter_dept = col_fd.selectbox("부 필터", ["전체"]+ALL_DEPTS, key="fd")
        filter_team = col_ft.selectbox("팀 필터", ["전체"]+ALL_TEAMS, key="ft")
        rows = []
        for uid, u in evaluatees.items():
            p    = profiles.get(uid, {})
            team = p.get("team", u.get("team",""))
            dept = get_team_dept(team)
            if filter_dept != "전체" and dept != filter_dept: continue
            if filter_team != "전체" and team != filter_team: continue
            ev     = evaluations.get(uid, {})
            result = calc_final(uid, evaluations, tasks_data)
            종합   = result.get("종합",{})
            rows.append({
                "이름": u.get("name",""), "소속부": dept, "소속팀": team,
                "직책": p.get("position",u.get("position","")),
                "직급": p.get("grade",u.get("grade","")),
                "과제": "✅" if tasks_data.get(uid,{}).get("tasks") else "❌",
                "PDF": "✅" if pdf_path(uid).exists() else "❌",
                "1차": "✅" if ev.get("1차") else "⏳",
                "2차": "✅" if ev.get("2차") else "⏳",
                "3차": "✅" if ev.get("3차") else "⏳",
                "4차": "✅" if ev.get("4차") else "⏳",
                "태도": "✅" if ev.get("deductions") is not None else "⏳",
                "최종": f"{종합['최종']:.1f}" if 종합.get("완료") else "-",
            })
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button("⬇️ CSV", data=df.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"평가현황_{datetime.now().strftime('%Y%m%d')}.csv",
                               mime="text/csv")
        else:
            st.info("해당 조건의 피평가자가 없습니다.")

    # ── 탭2 직무수행태도 ──────────────────────
    with tab2:
        st.subheader("🧘 직무수행태도 (C, 5점) 입력")
        st.caption("감점 항목 건수 입력 → 5점에서 자동 차감")
        st.divider()
        evaluations = get_evaluations()
        for uid, u in evaluatees.items():
            p    = profiles.get(uid, {})
            team = p.get("team", u.get("team",""))
            dept = get_team_dept(team)
            ev   = evaluations.get(uid, {})
            ded  = ev.get("deductions", {})
            att  = calc_attitude_score(ded)
            with st.expander(
                f"👤 {u.get('name','')}  ({dept}/{team}/{p.get('position',u.get('position',''))}) "
                f"— 태도점수: {att:.2f}점 / 5점", expanded=False
            ):
                with st.form(f"ded_{uid}"):
                    new_ded = {}
                    cl, cr = st.columns(2)
                    left_items  = list(DEDUCTION_RATES.items())[:6]
                    right_items = list(DEDUCTION_RATES.items())[6:]
                    with cl:
                        for item,(unit,rate) in left_items:
                            v = st.number_input(f"{item} ({unit}당 -{rate}점)",
                                                0, value=int(ded.get(item,0)), step=1,
                                                key=f"ded_{uid}_{item}")
                            new_ded[item] = v
                    with cr:
                        for item,(unit,rate) in right_items:
                            v = st.number_input(f"{item} ({unit}당 -{rate}점)",
                                                0, value=int(ded.get(item,0)), step=1,
                                                key=f"ded_{uid}_{item}")
                            new_ded[item] = v
                    preview = calc_attitude_score(new_ded)
                    st.markdown(f"총 감점: **{round(5-preview,2)}점** | 직무수행태도: **{preview:.2f}점**")
                    if st.form_submit_button("💾 저장", type="primary", use_container_width=True):
                        evaluations = get_evaluations()
                        evaluations.setdefault(uid,{})["deductions"] = new_ded
                        evaluations[uid]["deductions_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        save_json(EVALUATIONS_FILE, evaluations)
                        st.success(f"✅ {u.get('name','')} 직무수행태도 저장 완료."); st.rerun()

    # ── 탭3 점수 집계 ─────────────────────────
    with tab3:
        st.subheader("차수별 점수 상세")
        for uid, u in evaluatees.items():
            p      = profiles.get(uid, {})
            ev     = evaluations.get(uid, {})
            result = calc_final(uid, evaluations, tasks_data)
            종합   = result.get("종합",{})
            final  = 종합.get("최종",0)
            with st.expander(
                f"👤 {u.get('name','')} ({p.get('grade',u.get('grade',''))}) "
                f"— {'완료 '+str(final)+'점' if 종합.get('완료') else '진행중'}", expanded=False
            ):
                cols = st.columns(5)
                for i,(stage,weight) in enumerate(EVAL_WEIGHTS.items()):
                    with cols[i]:
                        st.markdown(f"**{stage}** ({int(weight*100)}%)")
                        if stage in result:
                            r = result[stage]
                            st.metric("A 근무실적", f"{r['A']:.1f}")
                            st.metric("B 직무능력", f"{r['B']:.1f}")
                            st.metric("소계 A+B",   f"{r['AB']:.1f}")
                            op = ev.get(stage,{}).get("opinion","")
                            if op: st.caption(f"의견: {op[:25]}…" if len(op)>25 else f"의견: {op}")
                        else:
                            st.caption("미평가")
                with cols[4]:
                    st.markdown("**종합**")
                    st.metric("가중A",   f"{종합.get('A_가중',0):.1f}")
                    st.metric("가중B",   f"{종합.get('B_가중',0):.1f}")
                    st.metric("태도C",   f"{종합.get('C',0):.1f}")
                    st.metric("최종합계", f"{final:.1f}점 ({grade_label(final)}등급)")

        st.divider()
        st.subheader("점수 분포")
        chart_rows = []
        for uid, u in evaluatees.items():
            r = calc_final(uid, evaluations, tasks_data)
            if r.get("종합",{}).get("완료"):
                chart_rows.append({"이름":u.get("name",""),"최종점수":r["종합"]["최종"]})
        if chart_rows:
            df_c = pd.DataFrame(chart_rows).sort_values("최종점수",ascending=False)
            st.bar_chart(df_c.set_index("이름")["최종점수"])

    # ── 탭4 직급별 순위 ───────────────────────
    with tab4:
        st.subheader("🏆 직급별 전사 통합 순위")
        st.caption("4차 평가 + 직무수행태도까지 완료된 피평가자만 집계됩니다.")
        df_rank = calc_grade_rankings(evaluations, tasks_data)

        if df_rank.empty:
            st.info("아직 전체 평가가 완료된 피평가자가 없습니다.")
        else:
            for grd in GRADES:
                df_g = df_rank[df_rank["직급"]==grd].copy()
                if df_g.empty: continue
                st.markdown(f"### 📌 {grd} 순위")
                disp = ["직급순위","이름","소속부","소속팀","직책",
                        "최종점수","근무실적(A)","직무능력(B)","직무태도(C)",
                        "1차 환산","2차 환산","3차 환산","4차 환산"]
                disp = [c for c in disp if c in df_g.columns]
                st.dataframe(df_g[disp].rename(columns={"직급순위":"순위"}),
                             use_container_width=True, hide_index=True)
                st.divider()

            all_cols = [c for c in ["직급","직급순위","이름","소속부","소속팀","직책",
                                     "최종점수","근무실적(A)","직무능력(B)","직무태도(C)",
                                     "1차 환산","2차 환산","3차 환산","4차 환산"]
                        if c in df_rank.columns]
            st.download_button("⬇️ 직급별 순위 CSV",
                               data=df_rank[all_cols].to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"직급별순위_{datetime.now().strftime('%Y%m%d')}.csv",
                               mime="text/csv")

    # ── 탭5 계정 관리 ─────────────────────────
    with tab5:
        st.subheader("🧑‍💼 계정·조직 관리")
        sub1, sub2, sub3 = st.tabs(["📥 엑셀 일괄 생성","✏️ 개별 계정 추가","📌 현재 계정 목록"])

        with sub1:
            col_dl, col_up = st.columns(2)
            with col_dl:
                with st.container(border=True):
                    st.markdown("**① 템플릿 다운로드**")
                    tpl = Path("account_template.xlsx")
                    if tpl.exists():
                        with open(tpl,"rb") as f:
                            st.download_button("⬇️ 템플릿 다운로드", data=f,
                                               file_name="계정생성_템플릿.xlsx",
                                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                               type="primary", use_container_width=True)
                    else:
                        st.warning("account_template.xlsx 를 앱 폴더에 넣어주세요.")
                    st.markdown("""
**컬럼 순서 (계정생성 시트)**
아이디 / 비밀번호 / 이름 / 직책 / 직급 / 소속팀 / 이메일
- 직책: 대표이사·본부장·부장·팀장·팀원
- 직급: 2급·3급·4급·5급·6급
- 소속팀: 행정지원팀·재정관리팀·생산관리팀·도담점·아름점·새롬점·소담점·직매장행정팀·공공급식팀
                    """)
            with col_up:
                with st.container(border=True):
                    st.markdown("**② 작성 완료 엑셀 업로드**")
                    xl = st.file_uploader("xlsx", type=["xlsx"],
                                          label_visibility="collapsed", key="acct_xl")

            if xl:
                fb = xl.read()
                ee_new, ev_new, errors = parse_account_excel_v3(fb)
                st.divider(); st.subheader("업로드 미리보기")
                if errors:
                    with st.expander(f"⚠️ 오류 {len(errors)}건", expanded=True):
                        for e in errors: st.warning(e)
                existing = get_users()
                for label, acc_dict in [("피평가자",ee_new),("평가자",ev_new)]:
                    if not acc_dict: continue
                    st.markdown(f"**{label} {len(acc_dict)}명**")
                    rows = [{"상태":"⚠️중복" if u in existing else "✅신규",
                             "아이디":u,"이름":v["name"],
                             "직책":v.get("position",""),"직급":v.get("grade",""),
                             "소속팀":v.get("team","")} for u,v in acc_dict.items()]
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

                if (ee_new or ev_new) and st.button("✅ 계정 생성 확정", type="primary"):
                    added_ee = added_ev = skipped = 0
                    for u, v in {**ee_new, **ev_new}.items():
                        if u not in existing:
                            existing[u] = v
                            if v.get("role")=="evaluatee": added_ee+=1
                            else: added_ev+=1
                        else: skipped+=1
                    save_json(USERS_FILE, existing)
                    st.success(f"완료! 피평가자 {added_ee}명, 평가자 {added_ev}명 | 스킵 {skipped}명")
                    st.rerun()

        with sub2:
            st.markdown("**새 계정 추가**")
            c1, c2 = st.columns(2)
            new_uid   = c1.text_input("아이디 *",    key="nu_uid")
            new_pw    = c2.text_input("비밀번호 *",  type="password", key="nu_pw")
            new_name  = c1.text_input("이름 *",      key="nu_name")
            new_role  = c2.selectbox("역할",         ["evaluatee (피평가자)","evaluator (평가자)"], key="nu_role")
            new_pos   = c1.selectbox("직책 *",       POSITIONS, key="nu_pos")
            new_grd   = c2.selectbox("직급 *",       GRADES,    key="nu_grd")

            # 직책에 따라 소속 부·팀 선택 동적 제어
            if new_pos in ("대표이사", "본부장"):
                c1.info("소속 부·팀 없음")
                c2.info("소속 부·팀 없음")
                new_dept = ""; new_team = ""
            elif new_pos == "부장":
                new_dept = c1.selectbox("소속 부 *", ALL_DEPTS, key="nu_dept")
                c2.info("부장은 소속 팀 없음")
                new_team = ""
            else:  # 팀장, 팀원
                new_dept = c1.selectbox("소속 부 *", ALL_DEPTS, key="nu_dept")
                new_team = c2.selectbox("소속 팀 *", ORG.get(new_dept, []), key="nu_team")

            new_email = c1.text_input("이메일", key="nu_email")

            if st.button("➕ 계정 추가", type="primary", key="nu_submit"):
                if not new_uid or not new_pw or not new_name:
                    st.error("아이디·비밀번호·이름은 필수입니다.")
                elif not is_valid_id(new_uid):
                    st.error("아이디는 영문·숫자·_ 만 허용됩니다.")
                elif new_pos in ("팀장","팀원") and not new_team:
                    st.error("팀장·팀원은 소속 팀이 필수입니다.")
                elif new_pos == "부장" and not new_dept:
                    st.error("부장은 소속 부가 필수입니다.")
                else:
                    users = get_users()
                    if new_uid in users:
                        st.error("이미 존재하는 아이디입니다.")
                    else:
                        users[new_uid] = {
                            "password": hash_pw(new_pw),
                            "role":     "evaluatee" if "evaluatee" in new_role else "evaluator",
                            "name":     new_name, "position": new_pos,
                            "grade":    new_grd,  "team":     new_team,
                            "dept":     new_dept, "email":    new_email,
                        }
                        save_json(USERS_FILE, users)
                        st.success(f"✅ {new_name} 계정 추가 완료!"); st.rerun()

        with sub3:
            all_u = get_users(); all_p = get_profiles()

            # 삭제 확인 상태 관리
            if "delete_confirm" not in st.session_state:
                st.session_state.delete_confirm = None

            # 삭제 확인 팝업
            if st.session_state.delete_confirm:
                del_uid  = st.session_state.delete_confirm
                del_name = all_u.get(del_uid, {}).get("name", del_uid)
                st.warning(f"⚠️ **'{del_name}' ({del_uid})** 계정을 삭제하시겠습니까?\n\n관련 평가 데이터·과제·인적사항도 함께 삭제됩니다.")
                cc1, cc2, _ = st.columns([1, 1, 3])
                if cc1.button("🗑️ 삭제 확정", type="primary", key="confirm_del"):
                    users_w = get_users()
                    if del_uid in users_w:
                        del users_w[del_uid]
                        save_json(USERS_FILE, users_w)
                    # 관련 데이터 정리
                    for fpath, getter in [(EVALUATIONS_FILE, get_evaluations),
                                          (TASKS_FILE, get_tasks),
                                          (PROFILES_FILE, get_profiles)]:
                        data = getter()
                        if del_uid in data:
                            del data[del_uid]
                            save_json(fpath, data)
                    # PDF 삭제
                    pp = pdf_path(del_uid)
                    if pp.exists(): pp.unlink()
                    st.session_state.delete_confirm = None
                    st.success(f"✅ '{del_name}' 계정이 삭제되었습니다.")
                    st.rerun()
                if cc2.button("취소", key="cancel_del"):
                    st.session_state.delete_confirm = None
                    st.rerun()
                st.divider()

            # 부별 계정 목록 + 삭제 버튼
            for dept, teams in ORG.items():
                st.markdown(f"#### 🏢 {dept}")
                dept_rows = []
                for uid, u in all_u.items():
                    if u.get("role") not in ("evaluatee", "evaluator"): continue
                    p    = all_p.get(uid, {})
                    team = p.get("team", u.get("team", ""))
                    if get_team_dept(team) != dept: continue
                    dept_rows.append((uid, u, p, team))

                if not dept_rows:
                    st.caption("등록된 계정 없음")
                    continue

                # 헤더
                hc = st.columns([1.5, 2, 1.5, 1.5, 1.5, 2, 1])
                for h, label in zip(hc, ["아이디","이름","역할","직책","직급","소속팀","삭제"]):
                    h.markdown(f"**{label}**")
                st.divider()

                for uid, u, p, team in dept_rows:
                    role_str = "피평가자" if u["role"] == "evaluatee" else "평가자"
                    rc = st.columns([1.5, 2, 1.5, 1.5, 1.5, 2, 1])
                    rc[0].caption(uid)
                    rc[1].markdown(u.get("name", ""))
                    rc[2].caption(role_str)
                    rc[3].caption(p.get("position", u.get("position", "")))
                    rc[4].caption(p.get("grade", u.get("grade", "")))
                    rc[5].caption(team)
                    if rc[6].button("🗑️", key=f"del_{uid}",
                                    help=f"{u.get('name','')} 계정 삭제"):
                        st.session_state.delete_confirm = uid
                        st.rerun()

            # ── 소속 없는 계정 (대표이사·본부장) & 기타 ──
            st.markdown("#### 👑 임원 (대표이사·본부장) 및 기타")
            etc_rows = []
            for uid, u in all_u.items():
                if u.get("role") not in ("evaluatee", "evaluator"): continue
                p    = all_p.get(uid, {})
                team = p.get("team", u.get("team", ""))
                pos  = p.get("position", u.get("position", ""))
                # 조직도에 소속되지 않은 경우 (팀이 비어있거나 인식 불가)
                if pos in ("대표이사", "본부장") or get_team_dept(team) == "":
                    etc_rows.append((uid, u, p, team))

            if etc_rows:
                hc = st.columns([1.5, 2, 1.5, 1.5, 1.5, 2, 1])
                for h, label in zip(hc, ["아이디","이름","역할","직책","직급","소속팀","삭제"]):
                    h.markdown(f"**{label}**")
                st.divider()
                for uid, u, p, team in etc_rows:
                    role_str = "피평가자" if u["role"] == "evaluatee" else "평가자"
                    rc = st.columns([1.5, 2, 1.5, 1.5, 1.5, 2, 1])
                    rc[0].caption(uid)
                    rc[1].markdown(u.get("name", ""))
                    rc[2].caption(role_str)
                    rc[3].caption(p.get("position", u.get("position", "")))
                    rc[4].caption(p.get("grade", u.get("grade", "")))
                    rc[5].caption(team if team else "-")
                    if rc[6].button("🗑️", key=f"del_{uid}",
                                    help=f"{u.get('name','')} 계정 삭제"):
                        st.session_state.delete_confirm = uid
                        st.rerun()
            else:
                st.caption("해당 계정 없음")

    # ── 탭6 평정표 다운로드 ───────────────────
    with tab6:
        st.subheader("📁 개인별 근무성적 평정표")
        for uid, u in evaluatees.items():
            p      = profiles.get(uid, {})
            result = calc_final(uid, evaluations, tasks_data)
            종합   = result.get("종합",{})
            status = "✅ 완료" if 종합.get("완료") else "⏳ 진행중"
            team   = p.get("team",u.get("team",""))
            ca, cb = st.columns([4,1])
            with ca:
                st.markdown(
                    f"**{u.get('name','')}** | {get_team_dept(team)}/{team} | "
                    f"{p.get('position',u.get('position',''))} ({p.get('grade',u.get('grade',''))}) | {status}"
                )
            with cb:
                xl_bytes = generate_eval_excel(uid, u, evaluations, tasks_data)
                st.download_button("⬇️ 평정표", data=xl_bytes,
                                   file_name=f"{u.get('name','')}_근무성적평정표.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                   key=f"dl_{uid}")


# ══════════════════════════════════════════════════════════════
# 엑셀 계정 파싱 v3
# ══════════════════════════════════════════════════════════════
def parse_account_excel_v3(file_bytes):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    ee_new, ev_new, errors = {}, {}, []
    if "계정생성" not in wb.sheetnames:
        errors.append("'계정생성' 시트를 찾을 수 없습니다."); return ee_new, ev_new, errors

    ws = wb["계정생성"]; cur_role = None
    for r_idx, row in enumerate(ws.iter_rows(values_only=True), 1):
        first = str(row[0]).strip() if row[0] else ""
        if "피평가자" in first and "evaluatee" in first.lower(): cur_role="evaluatee"; continue
        if "평가자"  in first and "evaluator" in first.lower():  cur_role="evaluator"; continue
        if "아이디"  in first: continue

        def cell(i): return str(row[i]).strip() if len(row)>i and row[i] not in (None,"None") else ""
        uid_raw=cell(0); pw_raw=cell(1); name_raw=cell(2)
        position=cell(3); grade=cell(4); team=cell(5); email=cell(6)

        if not uid_raw: continue
        if not is_valid_id(uid_raw): errors.append(f"행{r_idx}: '{uid_raw}' 아이디 오류"); continue
        if not pw_raw:   errors.append(f"행{r_idx}: '{uid_raw}' 비밀번호 없음"); continue
        if not name_raw: errors.append(f"행{r_idx}: '{uid_raw}' 이름 없음"); continue
        if position not in POSITIONS: errors.append(f"행{r_idx}: '{uid_raw}' 직책 오류({position})"); continue
        if grade    not in GRADES:    errors.append(f"행{r_idx}: '{uid_raw}' 직급 오류({grade})"); continue
        if team     not in ALL_TEAMS: errors.append(f"행{r_idx}: '{uid_raw}' 팀 오류({team})"); continue

        entry = {"password":hash_pw(pw_raw),"name":name_raw,"position":position,
                 "grade":grade,"team":team,"dept":get_team_dept(team),"email":email}
        if cur_role=="evaluatee": entry["role"]="evaluatee"; ee_new[uid_raw]=entry
        elif cur_role=="evaluator": entry["role"]="evaluator"; ev_new[uid_raw]=entry

    return ee_new, ev_new, errors


# ══════════════════════════════════════════════════════════════
# 개인 평정표 엑셀 생성
# ══════════════════════════════════════════════════════════════
def generate_eval_excel(ee_id, ee_info, evaluations, tasks_data):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    profiles = get_profiles()
    p      = profiles.get(ee_id, {})
    tasks  = tasks_data.get(ee_id, {}).get("tasks", [])
    ev     = evaluations.get(ee_id, {})
    result = calc_final(ee_id, evaluations, tasks_data)
    종합   = result.get("종합", {})

    wb = openpyxl.Workbook()
    ws = wb.active; ws.title="근무성적평정표"
    ws.sheet_view.showGridLines = False

    thin = Side(style="thin", color="AAAAAA")
    bdr  = Border(left=thin, right=thin, top=thin, bottom=thin)

    def hc(r,c,val,bg="1F4E79",fg="FFFFFF",bold=True,sz=10):
        cell=ws.cell(row=r,column=c,value=val)
        cell.font=Font(name="맑은 고딕",bold=bold,color=fg,size=sz)
        cell.fill=PatternFill("solid",start_color=bg)
        cell.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True)
        cell.border=bdr; return cell

    def dc(r,c,val,bold=False,align="left",bg="FFFFFF",sz=10):
        cell=ws.cell(row=r,column=c,value=val)
        cell.font=Font(name="맑은 고딕",bold=bold,size=sz)
        cell.fill=PatternFill("solid",start_color=bg)
        cell.alignment=Alignment(horizontal=align,vertical="center",wrap_text=True)
        cell.border=bdr; return cell

    def mc(r1,c1,r2,c2): ws.merge_cells(start_row=r1,start_column=c1,end_row=r2,end_column=c2)

    for i,w in enumerate([4,6,14,10,10,18,8,8,8,8],1):
        ws.column_dimensions[get_column_letter(i)].width=w

    team = p.get("team", ee_info.get("team",""))
    dept = get_team_dept(team)

    # 제목
    mc(1,1,1,10); hc(1,1,"근무성적 평정표",sz=14); ws.row_dimensions[1].height=35

    # 인적사항
    mc(2,1,2,10); hc(2,1,"□ 인적 사항",bg="2E75B6",sz=11)
    hc(3,1,"성명",bg="D6E4F0",fg="000000"); mc(3,2,3,3); dc(3,2,ee_info.get("name",""))
    hc(3,4,"소속부",bg="D6E4F0",fg="000000"); mc(3,5,3,6); dc(3,5,dept)
    hc(3,7,"소속팀",bg="D6E4F0",fg="000000"); mc(3,8,3,10); dc(3,8,team)
    hc(4,1,"직책",bg="D6E4F0",fg="000000"); mc(4,2,4,3)
    dc(4,2,p.get("position",ee_info.get("position","")))
    hc(4,4,"직급",bg="D6E4F0",fg="000000"); mc(4,5,4,6)
    dc(4,5,p.get("grade",ee_info.get("grade","")))
    hc(4,7,"입사일",bg="D6E4F0",fg="000000"); mc(4,8,4,10); dc(4,8,p.get("입사일",""))
    mc(5,1,5,10); dc(5,1,f"담당업무: {p.get('담당업무','')}",bg="EBF3FB",sz=9)

    row=6
    # 근무실적
    mc(row,1,row,10); hc(row,1,"2. 근무실적 평정 (A, 60점)",bg="2E75B6",sz=11)
    ws.row_dimensions[row].height=22; row+=1
    for c,(txt,bg) in enumerate([
        ("구분","375623"),("번호","375623"),("과제명","375623"),("비중","375623"),("주요실적","375623"),
        ("1차","1F4E79"),("2차","1F4E79"),("3차","1F4E79"),("4차","1F4E79"),("환산","C00000")
    ],1):
        hc(row,c,txt,bg=bg,sz=9)
    ws.row_dimensions[row].height=18; row+=1

    for t in tasks:
        dc(row,1,t["type"]); dc(row,2,t["no"],align="center")
        dc(row,3,t["title"]); dc(row,4,f"{t['weight']:.0%}",align="center")
        dc(row,5,t.get("result",""),bg="FAFAFA")
        conv_sum=0.0
        for j,stage in enumerate(EVAL_WEIGHTS):
            s=ev.get(stage,{}).get("tasks",{}).get(t["id"],"")
            dc(row,6+j,s if s!="" else "-",align="center")
            if isinstance(s,(int,float)): conv_sum+=s*t["weight"]*6
        avg_conv=round(conv_sum/4,2) if all(
            ev.get(st,{}).get("tasks",{}).get(t["id"]) is not None for st in EVAL_WEIGHTS) else "-"
        dc(row,10,avg_conv,align="center",bg="FFF2CC")
        ws.row_dimensions[row].height=40; row+=1

    mc(row,1,row,4); hc(row,1,"합계",bg="D6E4F0",fg="000000")
    for j,stage in enumerate(EVAL_WEIGHTS):
        dc(row,6+j,f"{calc_task_score(tasks,ev.get(stage,{})):.1f}",align="center",bold=True)
    dc(row,10,f"{종합.get('A_가중',0):.1f}",align="center",bold=True,bg="FFF2CC")
    ws.row_dimensions[row].height=18; row+=1

    # 직무수행능력
    mc(row,1,row,10); hc(row,1,"3-1. 직무수행능력 (B, 35점)",bg="2E75B6",sz=11)
    ws.row_dimensions[row].height=22; row+=1
    for c,txt in enumerate(["연번","","평정요소","배점","정의","1차","2차","3차","4차","소계"],1):
        hc(row,c,txt,bg="375623",sz=9)
    ws.row_dimensions[row].height=18; row+=1
    for i,(ab_name,ab_max,ab_def) in enumerate(ABILITY_ITEMS,1):
        mc(row,1,row,2); dc(row,1,i,align="center"); dc(row,3,ab_name)
        dc(row,4,ab_max,align="center"); dc(row,5,ab_def.replace("\n"," "),bg="FAFAFA")
        for j,stage in enumerate(EVAL_WEIGHTS):
            s=ev.get(stage,{}).get("ability",{}).get(ab_name,"")
            dc(row,6+j,s if s!="" else "-",align="center")
        dc(row,10,"-",align="center",bg="FFF2CC")
        ws.row_dimensions[row].height=28; row+=1
    mc(row,1,row,4); hc(row,1,"합계",bg="D6E4F0",fg="000000")
    for j,stage in enumerate(EVAL_WEIGHTS):
        dc(row,6+j,f"{calc_ability_score(ev.get(stage,{})):.0f}",align="center",bold=True)
    dc(row,10,f"{종합.get('B_가중',0):.1f}",align="center",bold=True,bg="FFF2CC")
    ws.row_dimensions[row].height=18; row+=1

    # 직무수행태도
    mc(row,1,row,10); hc(row,1,"3-2. 직무수행태도 (C, 5점)",bg="2E75B6",sz=11)
    ws.row_dimensions[row].height=22; row+=1
    deductions=ev.get("deductions",{})
    for item,(unit,rate) in DEDUCTION_RATES.items():
        mc(row,1,row,3); dc(row,1,item)
        dc(row,4,f"{unit}당 -{rate}점",align="center")
        dc(row,5,deductions.get(item,0),align="center")
        ws.row_dimensions[row].height=16; row+=1
    att_c=calc_attitude_score(deductions)
    mc(row,1,row,4); hc(row,1,"직무수행태도 합계",bg="D6E4F0",fg="000000")
    dc(row,5,f"{att_c:.2f}점",align="center",bold=True,bg="FFF2CC")
    ws.row_dimensions[row].height=18; row+=1

    # 종합평가
    mc(row,1,row,10); hc(row,1,"4. 종합평가",bg="2E75B6",sz=11)
    ws.row_dimensions[row].height=22; row+=1
    for c,txt in enumerate(["구분","","","","가중환산","1차(30%)","2차(30%)","3차(20%)","4차(20%)","비고"],1):
        hc(row,c,txt,bg="375623",sz=9)
    ws.row_dimensions[row].height=18; row+=1
    for label,gkey,bkey in [("근무실적(A,60점)","A_가중","A"),("직무수행능력(B,35점)","B_가중","B")]:
        mc(row,1,row,4); dc(row,1,label)
        dc(row,5,종합.get(gkey,0),align="center",bold=True,bg="FFF2CC")
        for j,stage in enumerate(EVAL_WEIGHTS):
            dc(row,6+j,result.get(stage,{}).get(bkey[-1],"-"),align="center")
        ws.row_dimensions[row].height=18; row+=1
    mc(row,1,row,4); hc(row,1,"소계(A+B)",bg="D6E4F0",fg="000000")
    dc(row,5,종합.get("AB_가중",0),align="center",bold=True,bg="FFF2CC")
    for j,stage in enumerate(EVAL_WEIGHTS):
        dc(row,6+j,result.get(stage,{}).get("AB","-"),align="center")
    ws.row_dimensions[row].height=18; row+=1
    mc(row,1,row,4); dc(row,1,"직무수행태도(C,5점)")
    dc(row,5,att_c,align="center",bold=True,bg="FFF2CC")
    ws.row_dimensions[row].height=18; row+=1
    mc(row,1,row,4); hc(row,1,"최종합계(100점)",bg="1F4E79",sz=11)
    dc(row,5,종합.get("최종",0),align="center",bold=True,bg="FFD700",sz=13)
    ws.row_dimensions[row].height=26; row+=1

    # 평정 의견
    mc(row,1,row,10); hc(row,1,"5. 평정 의견",bg="2E75B6",sz=11)
    ws.row_dimensions[row].height=22; row+=1
    for stage in EVAL_WEIGHTS:
        op=ev.get(stage,{}).get("opinion","")
        mc(row,1,row,2); hc(row,1,stage,bg="375623",sz=9)
        mc(row,3,row,10); dc(row,3,op,bg="FAFAFA")
        ws.row_dimensions[row].height=22; row+=1

    out=io.BytesIO(); wb.save(out); return out.getvalue()


# ══════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════
def main():
    st.set_page_config(page_title="근무성적 평정 시스템", page_icon="📋",
                       layout="wide", initial_sidebar_state="expanded")

    if not st.session_state.logged_in:
        show_login(); return

    users = get_users()
    u     = users.get(st.session_state.username, {})
    role  = st.session_state.role

    with st.sidebar:
        role_icon = {"evaluatee":"📄 피평가자","evaluator":"✍️ 평가자","admin":"🗂️ 총괄 관리자"}.get(role,"")
        st.markdown(f"### {role_icon}")
        st.markdown(f"**{st.session_state.name}** 님")
        if role == "evaluator":
            stage = get_stage_for_evaluator(st.session_state.username)
            st.caption(f"직책: {u.get('position','')} | 담당 차수: {stage}")
        if role in ("evaluatee","evaluator"):
            p    = get_profiles().get(st.session_state.username, {})
            team = p.get("team", u.get("team",""))
            st.caption(f"소속: {get_team_dept(team)} / {team}")
            st.caption(f"직급: {p.get('grade', u.get('grade',''))}")
        st.divider()
        if st.button("🚪 로그아웃", use_container_width=True):
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()

    if role=="evaluatee":   show_evaluatee()
    elif role=="evaluator": show_evaluator()
    elif role=="admin":     show_admin()
    else: st.error("알 수 없는 계정 유형입니다.")

if __name__ == "__main__":
    main()
