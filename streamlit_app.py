import csv
import io
import json
import random
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from html import escape, unescape

import requests
import streamlit as st


DATA_FILE = Path(__file__).with_name("french_words.json")
BADGES_FILE = Path(__file__).with_name("french_badges.json")
MILESTONE_THRESHOLDS = (
    1,
    10,
    25,
    50,
    100,
    250,
    500,
    1_000,
    2_500,
    5_000,
    10_000,
    25_000,
    50_000,
    100_000,
    250_000,
    500_000,
    1_000_000,
)
BADGE_TRACKS = (
    {"id": "daily", "label": "Today", "period": "day", "icon": "☀️"},
    {"id": "weekly", "label": "This week", "period": "week", "icon": "📅"},
    {"id": "monthly", "label": "This month", "period": "month", "icon": "🌙"},
    {"id": "yearly", "label": "This year", "period": "year", "icon": "🎆"},
    {"id": "lifetime", "label": "All time", "period": "all", "icon": "🌍"},
)
BADGE_COLORS = (
    ("#E4F3EC", "#225A49"),
    ("#E8EFFB", "#314E83"),
    ("#FFF0D9", "#80531A"),
    ("#FCE7E8", "#8A3640"),
    ("#EEE8FA", "#594180"),
    ("#DFF3F2", "#1D6562"),
    ("#FCEBDD", "#875020"),
)
EXAMPLE_FIELDS = (
    "example_french",
    "example_english",
    "example_source",
    "example_credit",
)


def load_words():
    if not DATA_FILE.exists():
        return []

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            words = json.load(file)
    except (json.JSONDecodeError, OSError):
        return []

    return words if isinstance(words, list) else []


def save_words(words):
    temporary_file = DATA_FILE.with_suffix(".json.tmp")
    with temporary_file.open("w", encoding="utf-8") as file:
        json.dump(words, file, ensure_ascii=False, indent=2)
    temporary_file.replace(DATA_FILE)


def remove_example(word):
    for field in EXAMPLE_FIELDS:
        word.pop(field, None)


def load_badges():
    if not BADGES_FILE.exists():
        return {}

    try:
        with BADGES_FILE.open("r", encoding="utf-8") as file:
            badges = json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}

    return badges if isinstance(badges, dict) else {}


def save_badges(badges):
    temporary_file = BADGES_FILE.with_suffix(".json.tmp")
    with temporary_file.open("w", encoding="utf-8") as file:
        json.dump(badges, file, ensure_ascii=False, indent=2)
    temporary_file.replace(BADGES_FILE)


def count_words_by_period(words, now):
    counts = {track["id"]: 0 for track in BADGE_TRACKS}
    counts["lifetime"] = len(words)
    current_iso_week = now.isocalendar()[:2]

    for word in words:
        created_at = word.get("created_at")
        if not created_at:
            continue
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            created = created.astimezone(timezone.utc)
        except (AttributeError, TypeError, ValueError):
            continue

        if created.date() == now.date():
            counts["daily"] += 1
        if created.isocalendar()[:2] == current_iso_week:
            counts["weekly"] += 1
        if (created.year, created.month) == (now.year, now.month):
            counts["monthly"] += 1
        if created.year == now.year:
            counts["yearly"] += 1

    return counts


def update_badges(words, now=None):
    now = now or datetime.now(timezone.utc)
    counts = count_words_by_period(words, now)
    badges = load_badges()
    changed = False

    for track_index, track in enumerate(BADGE_TRACKS):
        thresholds = MILESTONE_THRESHOLDS
        if track["id"] == "lifetime":
            thresholds = (*thresholds, 5_000_000_000)

        for tier_index, threshold in enumerate(thresholds):
            badge_id = f"{track['id']}-{threshold}"
            if counts[track["id"]] < threshold or badge_id in badges:
                continue
            background, foreground = BADGE_COLORS[(track_index + tier_index) % len(BADGE_COLORS)]
            badges[badge_id] = {
                "title": f"{track['label']} · {threshold:,} {'word' if threshold == 1 else 'words'}",
                "icon": track["icon"] if tier_index == 0 else ("🏅" if tier_index < 5 else "💎"),
                "background": background,
                "foreground": foreground,
                "earned_at": now.isoformat(timespec="seconds"),
                "track": track["id"],
                "threshold": threshold,
            }
            changed = True

    if changed:
        save_badges(badges)
    return counts, badges


def recommend_next_badge(counts, badges):
    recommendations = []
    for track in BADGE_TRACKS:
        thresholds = MILESTONE_THRESHOLDS
        if track["id"] == "lifetime":
            thresholds = (*thresholds, 5_000_000_000)
        for threshold in thresholds:
            badge_id = f"{track['id']}-{threshold}"
            if threshold > counts[track["id"]] and badge_id not in badges:
                recommendations.append(
                    (threshold - counts[track["id"]], track, threshold)
                )
                break

    return min(recommendations, key=lambda recommendation: recommendation[0]) if recommendations else None


def render_badge_grid(badges):
    for start in range(0, len(badges), 4):
        columns = st.columns(4)
        for column, badge in zip(columns, badges[start:start + 4]):
            with column:
                title = escape(str(badge.get("title", "Milestone")))
                icon = escape(str(badge.get("icon", "🏅")))
                earned_at = escape(str(badge.get("earned_at", ""))[:10])
                background = escape(str(badge.get("background", "#E8EFFB")))
                foreground = escape(str(badge.get("foreground", "#314E83")))
                st.markdown(
                    f"""<div class="badge-tile" style="background:{background};color:{foreground}">
                    <div class="badge-icon">{icon}</div>
                    <div class="badge-title">{title}</div>
                    <div class="badge-date">Earned {earned_at}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )


def translate_text(text, source_language, target_language):
    response = requests.get(
        "https://translate.googleapis.com/translate_a/single",
        params={
            "client": "gtx",
            "sl": source_language,
            "tl": target_language,
            "dt": "t",
            "q": text,
        },
        timeout=15,
    )
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, list) or not result or not isinstance(result[0], list):
        raise ValueError("Translation service returned an unexpected response.")
    translation = unescape("".join(segment[0] for segment in result[0] if segment and segment[0])).strip()
    if not translation:
        raise ValueError("Translation service returned an empty translation.")
    return translation


def normalize_tokens(text):
    normalized = unicodedata.normalize("NFKD", text.casefold())
    unaccented = "".join(character for character in normalized if not unicodedata.combining(character))
    return re.findall(r"[a-z0-9]+", unaccented)


def capitalize_initial(text):
    text = str(text or "").strip()
    for index, character in enumerate(text):
        if character.isalpha():
            return f"{text[:index]}{character.upper()}{text[index + 1:]}"
    return text


def build_quiz_questions(selected_entries, all_entries, direction):
    questions = []
    prompt_field, answer_field = (
        ("french", "english") if direction == "French → English" else ("english", "french")
    )
    all_answers = list(
        dict.fromkeys(
            str(entry.get(answer_field, "")).strip()
            for entry in all_entries
            if str(entry.get(answer_field, "")).strip()
        )
    )

    for entry in selected_entries:
        correct_answer = str(entry.get(answer_field, "")).strip()
        distractors = [
            answer for answer in all_answers if answer.casefold() != correct_answer.casefold()
        ]
        random.shuffle(distractors)
        choices = [correct_answer, *distractors[:3]]
        random.shuffle(choices)
        questions.append(
            {
                "prompt": str(entry.get(prompt_field, "")).strip(),
                "answer": correct_answer,
                "choices": choices,
            }
        )

    random.shuffle(questions)
    return questions


def fetch_dynamic_example(french, english=""):
    search_options = [("fra", "eng", french)]
    if english.strip():
        search_options.append(("eng", "fra", english))

    if not normalize_tokens(french):
        return None

    candidates = []
    for source_language, target_language, query in search_options:
        target_tokens = normalize_tokens(query)
        if not target_tokens:
            continue

        try:
            response = requests.get(
                "https://tatoeba.org/en/api_v0/search",
                params={
                    "from": source_language,
                    "to": target_language,
                    "query": query,
                    "orphans": "no",
                    "unapproved": "no",
                    "page": 1,
                },
                timeout=15,
            )
            response.raise_for_status()
            results = response.json().get("results", [])
        except (requests.RequestException, ValueError, AttributeError):
            continue

        for sentence in results:
            searched_sentence = sentence.get("text", "")
            sentence_tokens = normalize_tokens(searched_sentence)
            has_query = any(
                sentence_tokens[index:index + len(target_tokens)] == target_tokens
                for index in range(len(sentence_tokens) - len(target_tokens) + 1)
            )
            if not has_query:
                continue

            for translation_group in sentence.get("translations", []):
                for translation in translation_group:
                    if translation.get("lang") != target_language or not translation.get("isDirect"):
                        continue
                    translated_sentence = translation.get("text", "").strip()
                    if not translated_sentence:
                        continue

                    if source_language == "fra":
                        french_sentence = searched_sentence
                        english_sentence = translated_sentence
                        french_author = sentence.get("user", {}).get("username", "")
                        english_author = translation.get("author") or translation.get("user", {}).get("username", "")
                    else:
                        french_sentence = translated_sentence
                        english_sentence = searched_sentence
                        french_author = translation.get("author") or translation.get("user", {}).get("username", "")
                        english_author = sentence.get("user", {}).get("username", "")
                        french_tokens = normalize_tokens(french_sentence)
                        french_term_tokens = normalize_tokens(french)
                        exact_match = any(
                            french_tokens[index:index + len(french_term_tokens)] == french_term_tokens
                            for index in range(len(french_tokens) - len(french_term_tokens) + 1)
                        )
                        if not exact_match and len(french_term_tokens) == 1:
                            french_term = french_term_tokens[0]
                            stem = french_term[:-2] if french_term.endswith(("er", "ir", "re")) else ""
                            exact_match = bool(stem) and any(
                                token.startswith(stem) for token in french_tokens
                            )
                        if not exact_match:
                            continue

                    candidates.append(
                        {
                            "example_french": french_sentence,
                            "example_english": english_sentence,
                            "example_source": f"https://tatoeba.org/en/sentences/show/{sentence.get('id')}",
                            "example_credit": ", ".join(
                                credit for credit in (french_author, english_author) if credit
                            ),
                        }
                    )

    if candidates:
        return random.choice(candidates)

    target_tokens = normalize_tokens(french)
    if len(target_tokens) > 1:
        try:
            return {
                "example_french": french,
                "example_english": translate_text(french, "fr", "en"),
                "example_source": "",
                "example_credit": "",
            }
        except (requests.RequestException, ValueError, KeyError, TypeError):
            return None

    return None


st.set_page_config(page_title="French Website", page_icon="🇫🇷", layout="wide")
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@600;700&display=swap');
    :root {
        --ink: #203432;
        --muted: #687a75;
        --paper: #f7f6f0;
        --line: #dce4dc;
        --green: #276553;
        --coral: #dc725e;
    }
    .stApp { background: var(--paper); color: var(--ink); }
    [data-testid="stHeader"] { background: transparent; }
    .block-container { max-width: 1120px; padding-top: 2.5rem; padding-bottom: 4rem; }
    h1, h2, h3 { color: var(--ink); }
    h1 { font-family: 'Playfair Display', Georgia, serif; font-size: 2.8rem; }
    p, label, input, textarea, button, [data-testid="stCaptionContainer"] {
        font-family: 'DM Sans', sans-serif;
    }
    label, label p { color: var(--ink) !important; }
    .masthead { border-bottom: 1px solid var(--line); padding-bottom: 1.35rem; margin-bottom: 1.6rem; }
    .eyebrow { color: var(--coral); font-size: .76rem; font-weight: 700; text-transform: uppercase; letter-spacing: .12em; }
    .subtitle { color: var(--muted); margin-top: -.6rem; }
    .section-title { font-family: 'Playfair Display', Georgia, serif; font-size: 1.55rem; margin: .3rem 0 1rem; }
    .badge-tile { min-height: 112px; margin: .25rem 0 .65rem; padding: .8rem; border-radius: 8px; border: 1px solid rgba(32,52,50,.08); }
    .badge-icon { font-size: 1.5rem; line-height: 1.4; }
    .badge-title { font-weight: 700; font-size: .9rem; overflow-wrap: anywhere; }
    .badge-date { font-size: .72rem; opacity: .75; margin-top: .25rem; }
    [data-testid="stForm"] { background: #fffefa; border: 1px solid var(--line); border-radius: 8px; padding: 1.25rem; }
    div.stButton > button[kind="primary"] { background: var(--green); border-color: var(--green); }
    div.stButton > button[kind="primary"]:hover { background: #1e5143; border-color: #1e5143; }
    [data-testid="stMetric"] { background: #e9efe8; padding: .8rem 1rem; border-radius: 8px; }
    [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p,
    [data-testid="stMetricValue"], [data-testid="stMetricValue"] div {
        color: var(--ink) !important;
    }
    [data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

words = load_words()
milestone_counts, earned_badges = update_badges(words)
st.markdown(
    "<div class='masthead'><div class='eyebrow'>Your French, collected</div>",
    unsafe_allow_html=True,
)
st.title("French Website")
st.markdown(
    "<p class='subtitle'>A quiet place to keep the words you want to remember.</p></div>",
    unsafe_allow_html=True,
)

st.markdown("<div class='section-title'>Badges</div>", unsafe_allow_html=True)
badge_items = sorted(
    earned_badges.values(),
    key=lambda badge: badge.get("earned_at", ""),
    reverse=True,
)
recommendation = recommend_next_badge(milestone_counts, earned_badges)
if recommendation:
    remaining, next_track, next_threshold = recommendation
    st.info(
        f"Next badge: {next_track['label']} · {next_threshold:,} words. "
        f"Add {remaining:,} more {('word' if remaining == 1 else 'words')} to earn it."
    )
st.caption(
    "Words added: "
    f"today {milestone_counts['daily']:,} · this week {milestone_counts['weekly']:,} · "
    f"this month {milestone_counts['monthly']:,} · this year {milestone_counts['yearly']:,} · "
    f"all time {milestone_counts['lifetime']:,} · badges earned {len(badge_items):,}"
)
if badge_items:
    render_badge_grid(badge_items[:8])
    if len(badge_items) > 8:
        with st.expander(f"View all {len(badge_items):,} badges"):
            render_badge_grid(badge_items[8:])
else:
    st.caption("Your first badge is waiting. Save a French translation to begin.")

with st.expander("Make a 10-word quiz"):
    quiz_state = st.session_state.get("word_quiz")
    if quiz_state is None:
        if len(words) < 10:
            st.info(f"Save {10 - len(words)} more words to make a 10-word quiz.")
        else:
            selected_indices = st.multiselect(
                "Choose exactly 10 words",
                options=list(range(len(words))),
                format_func=lambda index: (
                    f"{capitalize_initial(words[index].get('french', ''))} — "
                    f"{capitalize_initial(words[index].get('english', ''))}"
                ),
                max_selections=10,
                key="quiz_word_selection",
            )
            direction = st.radio(
                "Quiz direction",
                ("French → English", "English → French"),
                horizontal=True,
                key="quiz_direction",
            )
            if st.button("Start quiz", type="primary", disabled=len(selected_indices) != 10):
                selected_entries = [words[index].copy() for index in selected_indices]
                st.session_state["word_quiz"] = {
                    "questions": build_quiz_questions(selected_entries, words, direction),
                    "score": 0,
                    "answers": [],
                    "current": 0,
                }
                st.rerun()
    else:
        questions = quiz_state["questions"]
        current_question = quiz_state["current"]
        if current_question < len(questions):
            question = questions[current_question]
            st.progress(current_question / len(questions), text=f"Question {current_question + 1} of 10")
            st.markdown(f"### {capitalize_initial(question['prompt'])}")
            with st.form(f"quiz_answer_{current_question}"):
                chosen_answer = st.radio(
                    "Choose the translation",
                    question["choices"],
                    format_func=capitalize_initial,
                )
                submitted_answer = st.form_submit_button(
                    "Check answer" if current_question < 9 else "Finish quiz",
                    type="primary",
                )
            if submitted_answer:
                is_correct = chosen_answer.casefold() == question["answer"].casefold()
                quiz_state["score"] += int(is_correct)
                quiz_state["answers"].append(
                    {
                        "prompt": question["prompt"],
                        "chosen": chosen_answer,
                        "answer": question["answer"],
                        "correct": is_correct,
                    }
                )
                quiz_state["current"] += 1
                st.rerun()
            if st.button("Exit quiz", key="exit_active_quiz"):
                del st.session_state["word_quiz"]
                st.rerun()
        else:
            st.progress(1.0, text="Quiz complete")
            score = quiz_state["score"]
            st.success(f"You scored {score} out of 10.")
            with st.expander("Review answers"):
                for answer_index, answer in enumerate(quiz_state["answers"], start=1):
                    status = "Correct" if answer["correct"] else "Review"
                    st.markdown(
                        f"{answer_index}. **{capitalize_initial(answer['prompt'])}**  \n"
                        f"Your answer: {capitalize_initial(answer['chosen'])} · {status}  \n"
                        f"Correct answer: {capitalize_initial(answer['answer'])}"
                    )
            if st.button("Make another quiz", type="primary", key="restart_quiz"):
                del st.session_state["word_quiz"]
                st.rerun()

entry_column, collection_column = st.columns([0.9, 1.3], gap="large")

with entry_column:
    st.markdown("<div class='section-title'>Add a word</div>", unsafe_allow_html=True)
    with st.form("word_entry", clear_on_submit=True):
        french = st.text_input("French word or phrase", placeholder="e.g. prendre son temps")
        submitted = st.form_submit_button("Save word", type="primary", use_container_width=True)

    if submitted:
        french = french.strip()
        if not french:
            st.error("Enter a French word or phrase.")
        elif any(item.get("french", "").casefold() == french.casefold() for item in words):
            st.warning("That French entry is already in your collection.")
        else:
            try:
                with st.spinner("Finding the translation and a matching example..."):
                    english = translate_text(french, "fr", "en")
                    example = fetch_dynamic_example(french, english)
                words.append(
                    {
                        "french": french,
                        "english": english,
                        "example_french": (example or {}).get("example_french", ""),
                        "example_english": (example or {}).get("example_english", ""),
                        "example_source": (example or {}).get("example_source", ""),
                        "example_credit": (example or {}).get("example_credit", ""),
                        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    }
                )
                save_words(words)
                st.success(f"Saved “{french}”.")
                st.rerun()
            except (requests.RequestException, ValueError, KeyError, TypeError) as error:
                st.error(f"Could not translate this entry: {error}")

    st.markdown("<div class='section-title'>English to French</div>", unsafe_allow_html=True)
    with st.form("english_to_french"):
        english_text = st.text_input(
            "English word or phrase",
            placeholder="e.g. See you tomorrow, madam",
        )
        translate_submitted = st.form_submit_button("Translate to French")

    if translate_submitted:
        st.session_state.pop("english_to_french_result", None)
        st.session_state.pop("english_to_french_error", None)
        st.session_state.pop("english_to_french_saved", None)
        english_text = english_text.strip()
        if not english_text:
            st.session_state["english_to_french_error"] = "Enter an English word or phrase."
        else:
            try:
                french_translation = translate_text(english_text, "en", "fr")
                st.session_state["english_to_french_result"] = french_translation
                existing_entry = next(
                    (
                        item
                        for item in words
                        if item.get("french", "").casefold() == french_translation.casefold()
                    ),
                    None,
                )
                if existing_entry:
                    st.session_state["english_to_french_saved"] = False
                else:
                    example = fetch_dynamic_example(french_translation, english_text)
                    words.append(
                        {
                            "french": french_translation,
                            "english": english_text,
                            "example_french": (example or {}).get("example_french", ""),
                            "example_english": (example or {}).get("example_english", ""),
                            "example_source": (example or {}).get("example_source", ""),
                            "example_credit": (example or {}).get("example_credit", ""),
                            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        }
                    )
                    save_words(words)
                    st.session_state["english_to_french_saved"] = True
                    st.rerun()
            except (requests.RequestException, ValueError, KeyError, TypeError) as error:
                st.session_state["english_to_french_error"] = f"Could not translate: {error}"

    if st.session_state.get("english_to_french_result"):
        st.markdown("**French translation**")
        st.info(st.session_state["english_to_french_result"])
        if st.session_state.get("english_to_french_saved") is True:
            st.success("Added to Words collected.")
        elif st.session_state.get("english_to_french_saved") is False:
            st.info("This French translation is already in Words collected.")
    if st.session_state.get("english_to_french_error"):
        st.error(st.session_state["english_to_french_error"])

with collection_column:
    st.markdown("<div class='section-title'>Your collection</div>", unsafe_allow_html=True)
    st.metric("Words collected", len(words))

    search = st.text_input("Search your words", placeholder="Search words or examples")
    query = search.strip().casefold()
    visible_words = [
        item
        for item in words
        if query
        and query
        in " ".join(
            (
                str(item.get("french", "")),
                str(item.get("english", "")),
                str(item.get("example_french", "")),
                str(item.get("example_english", "")),
            )
        ).casefold()
        or not query
    ]

    if visible_words:
        st.dataframe(
            [
                {
                    "French": capitalize_initial(item.get("french", "")),
                    "English": capitalize_initial(item.get("english", "")),
                    "French sentence": capitalize_initial(item.get("example_french", "")) or "—",
                    "English sentence": capitalize_initial(item.get("example_english", "")) or "—",
                    "Source": item.get("example_source", ""),
                    "Contributors": item.get("example_credit", ""),
                }
                for item in visible_words
            ],
            hide_index=True,
            use_container_width=True,
            height=430,
            row_height=38,
            column_config={
                "Source": st.column_config.LinkColumn("Source", display_text="Tatoeba")
            },
        )
    elif words:
        st.info("No entries match that search.")
    else:
        st.info("Your collection is empty. Add your first word to get started.")

    if words:
        with st.expander("Manage collection"):
            words_with_examples = [
                item
                for item in words
                if item.get("example_french") or item.get("example_english")
            ]
            if words_with_examples:
                st.markdown("**Delete an example sentence**")
                selected_example_index = st.selectbox(
                    "Choose a sentence to delete",
                    range(len(words_with_examples)),
                    format_func=lambda index: (
                        f"{words_with_examples[index].get('french', '')}: "
                        f"{words_with_examples[index].get('example_french') or words_with_examples[index].get('example_english', '')}"
                    ),
                    key="sentence_to_delete",
                )
                if st.button("Delete selected sentence"):
                    remove_example(words_with_examples[selected_example_index])
                    save_words(words)
                    st.rerun()

            words_without_examples = [item for item in words if not item.get("example_french")]
            if words_without_examples:
                st.markdown("**Add an example to a saved word**")
                word_for_example = st.selectbox(
                    "Choose a word",
                    [item["french"] for item in words_without_examples],
                    key="word_for_example",
                )
                if st.button("Find example sentence"):
                    selected_item = next(
                        item for item in words if item.get("french") == word_for_example
                    )
                    with st.spinner("Finding a matching example..."):
                        selected_item = next(
                            item for item in words if item.get("french") == word_for_example
                        )
                        example = fetch_dynamic_example(
                            word_for_example,
                            selected_item.get("english", ""),
                        )
                    if example:
                        selected_item.update(example)
                        save_words(words)
                        st.rerun()
                    st.info("No matching translated example was found for that entry.")

            st.markdown("**Delete a vocabulary entry**")
            selected_word_index = st.selectbox(
                "Choose the French-English row to delete",
                range(len(words)),
                index=None,
                placeholder="Choose an entry",
                format_func=lambda index: (
                    f"{words[index].get('french', '')} — {words[index].get('english', '')}"
                ),
                key="word_row_to_delete",
            )
            if st.button("Delete entire row", disabled=selected_word_index is None):
                del words[selected_word_index]
                save_words(words)
                st.rerun()
            csv_buffer = io.StringIO()
            csv_writer = csv.writer(csv_buffer)
            csv_writer.writerow(
                ["French", "English", "French sentence", "English sentence", "Source", "Contributors"]
            )
            csv_writer.writerows(
                [
                    capitalize_initial(item.get("french", "")),
                    capitalize_initial(item.get("english", "")),
                    capitalize_initial(item.get("example_french", "")),
                    capitalize_initial(item.get("example_english", "")),
                    item.get("example_source", ""),
                    item.get("example_credit", ""),
                ]
                for item in words
            )
            st.download_button(
                "Download as CSV",
                data=csv_buffer.getvalue(),
                file_name="french_words.csv",
                mime="text/csv",
            )