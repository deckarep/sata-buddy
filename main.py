import copy
import json
import random
import sys

from pyray import *
from raylib import ffi

SCREEN_WIDTH = 800
SCREEN_HEIGHT = 650

MARGIN_SIDE = 20
BUTT_WIDTH = 100
BUTT_SPACE = 10

QUESTION_COUNT = 20
QUESTION_IDX = 0

correct_tally = 0
wrong_tally = 0

questions = []

f = None  # font
titleTexture = None

# Need to maintain a handle to the ffi based booleans for checkboxes to work correctly.
# This is a limitation of the pyray api: https://github.com/electronstudio/raylib-python-cffi/issues/121
cb_state = [False] * 4 # holds the Python boolean state for each Checkbox.
cb_ptr_state = [ffi.new("bool *", b) for b in cb_state] # holds the pointers for each boolean in cb_state.


class GameState():
    TITLE =        -1
    START =        0
    SHOWING_CARD = 1
    GRADING_CARD = 2
    END =          3


game_state = GameState.TITLE

def int_to_color(val:int) -> Color:
    r = (val >> 32) & 0xff
    g = (val >> 16) & 0xff
    b = (val >> 8) & 0xff
    a = val  & 0xff
    return Color(r,g,b,a)

class Element():
    def __init__(self, discriminator: str, other: str):
        self.discriminator = discriminator
        self.other = other

    def __eq__(self, other):
        if isinstance(other, Element):
            return self.discriminator == other.discriminator
        return False

    def __hash__(self):
        return hash(self.discriminator)

    def __repr__(self):
        return f"<El: {self.__str__()}>"

    def __str__(self):
        if self.other.strip() == "":
            return self.discriminator
        return f"{self.discriminator}{self.other}"


def parse_element(val: str) -> Element:
    if not "(" in val:
        return Element(val, "")
    else:
        parts = val.split("(")
        return Element(parts[0], "(" + parts[1])


def fill_set(options_set, fill_set):
    assert len(fill_set) < 4, "a set must be provided that is not full!!"

    options_list = list(options_set)
    while len(fill_set) < 4:
        # When dupes are encountered, the len shouldn't change and so it should keep going.
        fill_set.add(one_of(options_list))

    assert len(fill_set) == 4, "the set must have 4 elements"


def one_of(some_list):
    return some_list[random.randint(0, len(some_list) - 1)]

def choose_range(some_list, frm:int, to:int) -> list:
    # if a set was passed in, convert to list first.
    if not isinstance(some_list, list):
        some_list = list(some_list)

    how_many = random.randint(frm, to)
    selected = set()

    while len(selected) != how_many:
        selected.add(one_of(some_list))

    return list(selected)

def choose_incorrect(super_set:set, all_answers:set, how_many:int) -> list:
    selected = set()

    left_over = super_set.difference(all_answers)
    how_many = min(how_many, len(left_over))

    # Using a target set ensures we don't have dupes.
    while len(selected) != how_many:
        val = super_set.pop()

        # Ensure we don't add a duplicate correct answer.
        if val in all_answers:
            super_set.add(val)
            continue

        selected.add(val)
        # Put back what you took out, there is no other way to do this without copying entire list.
        super_set.add(val)

    return list(selected)

def question_by_title(txt:str, tag:str, super_set:dict, deck:list) -> dict:
    # 1. for the tag type provided choose 4 possible options
    how_many_correct = random.randint(1, 3)
    pivot_choice = one_of(list(super_set[tag]))

    # 0. Dev note: this brute force and re-processing of set logic is stupid.
    # It's not efficient, but I'm racing the clock to help the wife with her study habit
    # She is a nursing student and needs this now, I can always optimize later.

    # 1. populate correct answers first
    selected_chosen_answers = set()
    max_attempts = 100 # yes a hack.
    tries = 0
    while len(selected_chosen_answers) != how_many_correct:
        tmp = one_of(deck)
        if pivot_choice in set([s.strip() for s in tmp.get(tag).split("/")]):
            selected_chosen_answers.add(tmp.get("subject"))
        if tries > max_attempts:
            break
        tries +=1

    assert len(selected_chosen_answers) >= 1, "at least one answer must exist!!"

    # 2. now select only wrong answers for the remaining.
    wrong_answers = set()
    left_over = 4 - how_many_correct
    max_attempts = len(deck)
    tries = 0
    while (len(wrong_answers) != left_over):
        tmp = one_of(deck)
        if pivot_choice not in set([s.strip() for s in tmp.get(tag).split("/")]):
            wrong_answers.add(tmp.get("subject"))
        if tries > max_attempts:
            break
        tries +=1

    presented = list(selected_chosen_answers | wrong_answers)
    user = [False] * len(presented)
    answers = [True if s in selected_chosen_answers else False for s in presented]

    return {
        "q": txt.replace("{title}", pivot_choice),
        "choices": presented,
        "user": user,
        "a": answers,
    }

def question_by_tag(txt:str, tag:str, super_set:dict, deck:list) -> dict:
    # 1. Select random disease.
    rand_disease = one_of(deck)
    title = rand_disease.get("subject")
    all_possible_answers = set([s.strip() for s in rand_disease.get(tag).split("/")])

    # 2. Choose 1 to 3 correct answers from category
    selected_chosen_answers = choose_range(all_possible_answers, 1, min(3, len(all_possible_answers)))

    # 3. Choose remaining incorrect answers
    selected_wrong_answers = choose_incorrect(super_set[tag], all_possible_answers, 4 - len(selected_chosen_answers))

    presented_answers = set(selected_chosen_answers) | set(selected_wrong_answers)

    # Going to support between 2-4 answers (inclusive).
    # Some answers like yes or no, impossible to have more than 2 options! Should add maybe?
    assert 1 < len(presented_answers) <= 4, "final presented answers must be 4 only!"

    presented = list(presented_answers)

    # 4. Build answers boolean table.
    answers = []
    for p in presented:
        if p in selected_chosen_answers:
            answers.append(True)
        else:
            answers.append(False)

    user = [False] * len(presented)

    return {
        "q": txt.replace("{title}", title),
        "choices": presented,
        "user": user,
        "a": answers,
    }

question_builders = [
    # Regular style
    ("Which signs & symptoms are present in: {title}?", "signs-symptoms", question_by_tag),
    ("Which nursing interventions apply to: {title}?", "nursing-interventions", question_by_tag),
    ("{title} may have what complications?", "complications", question_by_tag),
    ("A vaccine exists for {title}?", "vaccine-available", question_by_tag),
    ("What is the microbial form of {title}?", "microbe-form", question_by_tag),
    ("What method of transmission occurs for {title}?", "transmission", question_by_tag),

    # Pivot style
    ("Select all diseases where a vaccine exists?", "vaccine-available", question_by_title),
    ("Select all diseases with a \"{title}\" complication?", "complications", question_by_title),
    ("Select all diseases with a \"{title}\" transmission mode?", "transmission", question_by_title),
    ("Select all diseases with a sign/symptom of \"{title}\"?", "signs-symptoms", question_by_title),
    ("Select all diseases with the following nursing intervention: {title}?", "nursing-interventions", question_by_title),
]


def load_build_sata():
    questions.clear()
    super_set = {}
    with open("decks/contagious_diseases.json", 'r') as deck:
        doc = json.load(deck)
        for i, card in enumerate(doc["decks"]):
            for k, v in card.items():
                if not super_set.get(k):
                    super_set[k] = set()
                if "/" in v:
                    parts = v.split("/")
                    for s in parts:
                        super_set[k].add(s.strip())  # parse_element(s))
                else:
                    super_set[k].add(v)  # parse_element(v))

    # Ensure some degree of uniqueness via question + choices combinations to mitigate redundancy.
    track_dupes = set()
    while len(questions) < QUESTION_COUNT:
        txt, tag, q_builder = one_of(question_builders)
        new_question = q_builder(txt, tag, super_set, doc["decks"])
        # If we generated a question that has no answers, throw it out for now.
        # In the future find this bug!
        has_answer = False
        for a in new_question.get('a'):
            if a == True:
                has_answer = True
                break

        if not has_answer:
            # TODO: find out why this happens and fix it.
            print("Throwing out a question because no answers were found!!")
            print(new_question)
            continue

        title = new_question.get('q')
        # for now, will consider choices in various order as unique
        choices = ",".join(sorted(new_question.get('choices')))
        unique = f"{title} {choices}"
        if new_question.get("q") in track_dupes:
            print(f"Question len: {len(questions)} -- throwing out duplicate question: ", unique)
            continue
        track_dupes.add(unique)
        #print(f"Question added: {unique}")
        questions.append(new_question)


def init_game():
    global wrong_tally, correct_tally, QUESTION_IDX, game_state
    QUESTION_IDX = correct_tally  = wrong_tally = 0
    load_build_sata()

    game_state = GameState.SHOWING_CARD


def render_title_screen():
    global game_state

    rl_push_matrix()
    rl_scalef(0.75, 0.7, 0)
    draw_texture_ex(titleTexture, Vector2(0, 0), 0, 1.0, WHITE)
    rl_pop_matrix()
    if gui_button(Rectangle((SCREEN_WIDTH>>1) - (110>>1), SCREEN_HEIGHT - 60, 110, 40), "Let's Go!"):
        game_state = GameState.START
    if gui_button(Rectangle(SCREEN_WIDTH - 80, 10, 60, 40), "Exit"):
        sys.exit()

def render_show_card():
    global game_state, wrong_tally, correct_tally, QUESTION_IDX

    quizItem = questions[QUESTION_IDX]
    title = quizItem.get('q')
    answers = quizItem.get('a')
    choices = quizItem.get('choices')
    user = quizItem.get('user')

    gui_label(Rectangle(MARGIN_SIDE, -20, 300, 100), f"Question {QUESTION_IDX + 1} of {len(questions)}:")
    gui_text_box(Rectangle(MARGIN_SIDE, 50, SCREEN_WIDTH - (MARGIN_SIDE * 2), 180), title, 20, False)

    padding_y = 45
    for idx in range(len(choices)):
        gui_check_box(Rectangle(30, 250 + (idx * padding_y), 40, 40), "", user[idx])
        #gui_check_box(Rectangle(30, 250 + (idx * padding_y), 40, 40), "", cb_ptr_state[idx])
        if gui_button(Rectangle(60 + 30, 250 + (idx * padding_y), SCREEN_WIDTH - (MARGIN_SIDE * 5) - 8, 40),
                      f"{chr(65 + idx)}.) {choices[idx]}"):
            user[idx] = not user[idx]

    rec = Rectangle(MARGIN_SIDE + BUTT_WIDTH + 5, SCREEN_HEIGHT - 60, BUTT_WIDTH + 80, 40)
    if (gui_button(rec, gui_icon_text(GuiIconName.ICON_FX, "Continue"))):
        if game_state == GameState.SHOWING_CARD:
            is_correct = True
            for idx, user_answer in enumerate(user):
                if user_answer != answers[idx]:
                    # if at least one was wrong, flag the whole question as wrong.
                    is_correct = False
                    break

            if is_correct:
                correct_tally += 1
            else:
                wrong_tally += 1
            game_state = GameState.GRADING_CARD
        elif game_state == GameState.GRADING_CARD:
            QUESTION_IDX += 1

            if QUESTION_IDX == len(questions):
                QUESTION_IDX = 0
                game_state = GameState.END
            else:
                game_state = GameState.SHOWING_CARD


def render_grade_card():
    global f

    quizItem = questions[QUESTION_IDX]
    answers = quizItem.get('a')
    user = quizItem.get('user')

    is_correct = True

    padding_y = 45
    for idx, user_answer in enumerate(user):
        if user_answer != answers[idx]:
            # if at least one was wrong, flag the whole question as wrong.
            is_correct = False
        if answers[idx]:
            draw_rectangle(MARGIN_SIDE + 10, 249 + (idx * padding_y), 750, 40, Color(0, 255, 0, 65))

    if is_correct:
        draw_text_ex(f, "CORRECT", Vector2(330, 525), 44, 0, GREEN)
    else:
        draw_text_ex(f, "WRONG", Vector2(330, 525), 44, 0, RED)


def render_end():
    global correct_tally, wrong_tally, QUESTION_IDX, game_state

    score = (correct_tally / len(questions))
    gui_label(Rectangle(60, 60, 400, 40), f"Final Score: {score:.1%}")
    rec = Rectangle(MARGIN_SIDE + BUTT_WIDTH + 5, SCREEN_HEIGHT - 60, BUTT_WIDTH + 80, 40)
    if (gui_button(rec, gui_icon_text(GuiIconName.ICON_FX, "Start Over"))):
        load_build_sata()
        correct_tally = wrong_tally = 0
        QUESTION_IDX = 0
        game_state = GameState.SHOWING_CARD

    rec = Rectangle(MARGIN_SIDE + (BUTT_WIDTH + 5) * 3, SCREEN_HEIGHT - 60, BUTT_WIDTH + 80, 40)
    if (gui_button(rec, gui_icon_text(GuiIconName.ICON_FX, "Leave"))):
        game_state = GameState.TITLE


def main():
    global f, titleTexture

    init_window(SCREEN_WIDTH, SCREEN_HEIGHT, "SATA Buddy - A study intervention program - 0.1")
    set_exit_key(KeyboardKey.KEY_ESCAPE)
    set_target_fps(30)

    f = load_font("font/Bookerly Bold.ttf")
    gui_set_font(f)

    titleTexture = load_texture("assets/title.png")

    gui_set_style(GuiControl.DEFAULT, GuiDefaultProperty.TEXT_SIZE, 30)
    gui_set_style(GuiControl.DEFAULT, GuiDefaultProperty.TEXT_WRAP_MODE, GuiTextWrapMode.TEXT_WRAP_WORD)
    gui_set_style(GuiControl.DEFAULT, GuiDefaultProperty.TEXT_LINE_SPACING, 30)
    gui_set_style(GuiControl.CHECKBOX, GuiControlProperty.TEXT_PADDING, 10)
    gui_set_style(GuiControl.BUTTON, GuiControlProperty.TEXT_ALIGNMENT, GuiTextAlignment.TEXT_ALIGN_LEFT)
    gui_set_style(GuiControl.BUTTON, GuiControlProperty.TEXT_PADDING, 2)
    gui_set_style(GuiControl.TEXTBOX, GuiDefaultProperty.TEXT_SIZE, 25)
    gui_set_style(GuiControl.TEXTBOX, GuiControlProperty.TEXT_PADDING, 2)
    backColor = int_to_color(gui_get_style(GuiControl.DEFAULT, GuiDefaultProperty.BACKGROUND_COLOR))

    while not window_should_close():
        begin_drawing()
        clear_background(backColor)

        if game_state == GameState.TITLE:
            render_title_screen()
        elif game_state == GameState.START:
            init_game()
        if game_state == GameState.SHOWING_CARD:
            render_show_card()
        elif game_state == GameState.GRADING_CARD:
            render_show_card()
            render_grade_card()
        elif game_state == GameState.END:
            render_end()

        # Always rendered no matter state
        if not game_state == GameState.TITLE:
            gui_label(Rectangle(SCREEN_WIDTH - 280, -20, 300, 100), f"Correct: {correct_tally}, Wrong: {wrong_tally}")
        end_drawing()
    close_window()

main()
