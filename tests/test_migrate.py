#!/usr/bin/env python3
"""
notion-migrate-worklogs 파서 유닛 테스트
Run: python3 tests/test_migrate.py
"""

import sys, os, re, unittest, textwrap

# ── 파서 (notion-migrate-worklogs.sh 와 동일 로직) ──────────────────────────

def parse_number(s):
    return int(re.sub(r'[^\d]', '', s))

def parse_token_section(text):
    result = {
        'model': 'claude-opus-4-6',
        'tokens': 0,
        'cost': 0.0,
        'duration': 0,
        'daily_tokens': 0,
        'daily_cost': 0.0,
    }
    for line in text.split('\n'):
        line = line.strip().lstrip('- ')
        if line.startswith('모델:'):
            result['model'] = line.split(':', 1)[1].strip()
        elif line.startswith('이번 작업:'):
            m = re.search(r'([\d,]+)\s*토큰\s*/\s*\$([\d.]+)', line)
            if m:
                result['tokens'] = parse_number(m.group(1))
                result['cost']   = float(m.group(2))
            else:
                m2 = re.search(r'\$([\d.]+)', line)
                if m2:
                    result['cost'] = float(m2.group(1))
        elif line.startswith('소요 시간:'):
            m = re.search(r'(\d+)', line)
            if m:
                result['duration'] = int(m.group(1))
        elif line.startswith('일일 누적:'):
            m = re.search(r'([\d,]+)\s*토큰\s*/\s*\$([\d.]+)', line)
            if m:
                result['daily_tokens'] = parse_number(m.group(1))
                result['daily_cost']   = float(m.group(2))
    return result

def parse_entry(date, project, entry_text):
    lines = entry_text.strip().split('\n')
    if not lines:
        return None
    time_match = re.match(r'^## (\d{2}:\d{2})', lines[0])
    if not time_match:
        return None
    time_str = time_match.group(1)

    sections = {}
    cur_name, cur_lines = None, []
    for line in lines[1:]:
        if line.startswith('### '):
            if cur_name is not None:
                sections[cur_name] = '\n'.join(cur_lines).strip()
            cur_name  = line[4:].strip()
            cur_lines = []
        else:
            cur_lines.append(line)
    if cur_name is not None:
        sections[cur_name] = '\n'.join(cur_lines).strip()

    title = f"{date} {time_str}"
    for sec in ['요청사항', '작업 내용']:
        for line in sections.get(sec, '').split('\n'):
            line = line.strip().lstrip('- ')
            if line:
                title = line[:100]
                break
        if title != f"{date} {time_str}":
            break

    token_info = parse_token_section(sections.get('토큰 사용량', ''))

    parts = []
    for sec in ['요청사항', '작업 내용', '변경 파일', '토큰 사용량']:
        if sections.get(sec, '').strip():
            parts.append(f"### {sec}\n{sections[sec]}")
    content = '\n\n'.join(parts)

    return {'date': date, 'time': time_str, 'project': project,
            'title': title, 'content': content, **token_info}

def parse_file_text(text, date='2026-01-01', default_project='.claude'):
    project = default_project
    m = re.match(r'^# Worklog:\s*(.+?)\s*—', text)
    if m:
        project = m.group(1).strip()

    blocks, current = [], []
    for line in text.split('\n'):
        if re.match(r'^## \d{2}:\d{2}', line) and current:
            blocks.append('\n'.join(current))
            current = [line]
        elif re.match(r'^## \d{2}:\d{2}', line):
            current = [line]
        elif current:
            current.append(line)
    if current:
        blocks.append('\n'.join(current))

    return [e for e in (parse_entry(date, project, b) for b in blocks) if e]


# ── 테스트 ───────────────────────────────────────────────────────────────────

SAMPLE_FULL = textwrap.dedent("""\
    # Worklog: my-project — 2026-02-23

    ---

    ## 10:04

    ### 요청사항
    - 에이전트 파일 검토 후 frontmatter description 보강

    ### 작업 내용
    - 5개 에이전트에 상세한 YAML frontmatter description 추가

    ### 변경 파일
    - `agents/lead.md`: frontmatter description 추가

    ### 토큰 사용량
    - 모델: claude-opus-4-6
    - 이번 작업: 56,550,853 토큰 / $37.47
    - 소요 시간: 15분
    - 일일 누적: 56,550,853 토큰 / $37.47

    ---

    ## 10:07

    ### 요청사항
    - 이전 세션에서 미커밋된 변경사항 커밋

    ### 작업 내용
    - commands/dev.md에 규모 판별 로직 추가

    ### 토큰 사용량
    - 모델: claude-sonnet-4-6
    - 이번 작업: 39,696,835 토큰 / $23.93
    - 소요 시간: 4분
    - 일일 누적: 96,247,688 토큰 / $61.40
""")

SAMPLE_AUTO = textwrap.dedent("""\
    # Worklog: .claude — 2026-03-01

    ---

    ## 11:29 (auto)

    ### 작업 내용
    - fix: 설정 변경

    ### 변경 파일
    - `settings.json`
""")

SAMPLE_NO_TOKEN = textwrap.dedent("""\
    # Worklog: .claude — 2026-02-28

    ---

    ## 09:00

    ### 요청사항
    - 빠른 수정

    ### 작업 내용
    - 한 줄 수정
""")


class TestParseTokenSection(unittest.TestCase):
    def test_full_token_line(self):
        text = "- 모델: claude-opus-4-6\n- 이번 작업: 56,550,853 토큰 / $37.47\n- 소요 시간: 15분\n- 일일 누적: 96,247,688 토큰 / $61.40"
        r = parse_token_section(text)
        self.assertEqual(r['model'], 'claude-opus-4-6')
        self.assertEqual(r['tokens'], 56_550_853)
        self.assertAlmostEqual(r['cost'], 37.47)
        self.assertEqual(r['duration'], 15)
        self.assertEqual(r['daily_tokens'], 96_247_688)
        self.assertAlmostEqual(r['daily_cost'], 61.40)

    def test_empty_section(self):
        r = parse_token_section('')
        self.assertEqual(r['tokens'], 0)
        self.assertEqual(r['cost'], 0.0)
        self.assertEqual(r['model'], 'claude-opus-4-6')

    def test_cost_with_many_decimals(self):
        text = "- 이번 작업: 3,181,115 토큰 / $1.3199667\n- 일일 누적: 1,255,312,387 토큰 / $720.3599667"
        r = parse_token_section(text)
        self.assertEqual(r['tokens'], 3_181_115)
        self.assertAlmostEqual(r['cost'], 1.3199667, places=6)
        self.assertEqual(r['daily_tokens'], 1_255_312_387)

    def test_cost_only_format(self):
        """토큰 없이 비용만 있는 신형 형식: 이번 작업: $1.416"""
        text = "- 모델: claude-sonnet-4-6\n- 이번 작업: $1.416"
        r = parse_token_section(text)
        self.assertEqual(r['tokens'], 0)
        self.assertAlmostEqual(r['cost'], 1.416, places=3)
        self.assertEqual(r['model'], 'claude-sonnet-4-6')

    def test_cost_only_format_many_decimals(self):
        text = "- 이번 작업: $0.8207073000"
        r = parse_token_section(text)
        self.assertAlmostEqual(r['cost'], 0.8207073, places=6)
        self.assertEqual(r['tokens'], 0)


class TestParseEntry(unittest.TestCase):
    ENTRY = textwrap.dedent("""\
        ## 10:04

        ### 요청사항
        - 에이전트 파일 검토 후 frontmatter description 보강

        ### 작업 내용
        - 5개 에이전트에 YAML 추가

        ### 토큰 사용량
        - 모델: claude-opus-4-6
        - 이번 작업: 56,550,853 토큰 / $37.47
        - 소요 시간: 15분
        - 일일 누적: 56,550,853 토큰 / $37.47
    """)

    def test_time(self):
        e = parse_entry('2026-02-23', 'proj', self.ENTRY)
        self.assertEqual(e['time'], '10:04')

    def test_title_from_요청사항(self):
        e = parse_entry('2026-02-23', 'proj', self.ENTRY)
        self.assertEqual(e['title'], '에이전트 파일 검토 후 frontmatter description 보강')

    def test_tokens(self):
        e = parse_entry('2026-02-23', 'proj', self.ENTRY)
        self.assertEqual(e['tokens'], 56_550_853)
        self.assertAlmostEqual(e['cost'], 37.47)
        self.assertEqual(e['duration'], 15)

    def test_invalid_entry_returns_none(self):
        self.assertIsNone(parse_entry('2026-02-23', 'proj', '## invalid\nno time'))


class TestParseFileText(unittest.TestCase):
    def test_full_sample_entry_count(self):
        entries = parse_file_text(SAMPLE_FULL, '2026-02-23')
        self.assertEqual(len(entries), 2)

    def test_project_extracted_from_header(self):
        entries = parse_file_text(SAMPLE_FULL, '2026-02-23')
        self.assertEqual(entries[0]['project'], 'my-project')

    def test_second_entry_model(self):
        entries = parse_file_text(SAMPLE_FULL, '2026-02-23')
        self.assertEqual(entries[1]['model'], 'claude-sonnet-4-6')

    def test_auto_entry_parsed(self):
        """(auto) 태그 항목도 HH:MM 매칭으로 파싱되고 토큰은 0"""
        entries = parse_file_text(SAMPLE_AUTO, '2026-03-01')
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['time'], '11:29')
        self.assertEqual(entries[0]['tokens'], 0)
        self.assertEqual(entries[0]['cost'], 0.0)

    def test_no_token_section(self):
        """토큰 사용량 섹션 없어도 파싱 성공, 기본값 0"""
        entries = parse_file_text(SAMPLE_NO_TOKEN, '2026-02-28')
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]['tokens'], 0)
        self.assertEqual(entries[0]['duration'], 0)

    def test_title_falls_back_to_작업내용(self):
        """요청사항 없으면 작업 내용으로 title fallback"""
        text = textwrap.dedent("""\
            # Worklog: .claude — 2026-01-01

            ## 09:00

            ### 작업 내용
            - 설정 파일 수정
        """)
        entries = parse_file_text(text, '2026-01-01')
        self.assertEqual(entries[0]['title'], '설정 파일 수정')

    def test_content_contains_sections(self):
        entries = parse_file_text(SAMPLE_FULL, '2026-02-23')
        self.assertIn('### 요청사항', entries[0]['content'])
        self.assertIn('### 변경 파일', entries[0]['content'])

    def test_date_from_param(self):
        entries = parse_file_text(SAMPLE_FULL, '2026-02-23')
        self.assertEqual(entries[0]['date'], '2026-02-23')


class TestParseNumber(unittest.TestCase):
    def test_comma_separated(self):
        self.assertEqual(parse_number('56,550,853'), 56_550_853)

    def test_plain(self):
        self.assertEqual(parse_number('12345'), 12345)

    def test_large(self):
        self.assertEqual(parse_number('1,255,312,387'), 1_255_312_387)


if __name__ == '__main__':
    result = unittest.main(verbosity=2, exit=False)
    sys.exit(0 if result.result.wasSuccessful() else 1)
