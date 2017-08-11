import curses
curses.KEY_ENTER = 10

import itertools

class Chooser:

    CHOICE_INDENTATION = 2
    NUM_QUESTION_LINES = 1
    TAG = ' ...'

    def __init__(self, question, choices):
        self.num_choices = len(choices)
        self.question = self.truncate(question)
        pattern = ' ' * self.CHOICE_INDENTATION + '[{{:>{wid}}}] {{}}'.format(
            wid=len(str(len(choices) - 1))
        )
        self.choices = tuple(map(
            self.truncate,
            itertools.starmap(pattern.format, enumerate(choices))
        ))
        self.emphasized = list(itertools.repeat(False, curses.LINES))
        self.emphasized[0] = True

    @classmethod
    def truncate(cls, line):
        return (
            line if len(line) <= curses.COLS
            else line[: curses.COLS - len(cls.TAG)] + cls.TAG
        )

    @classmethod
    def choice_index(cls, i, j):
        if j < cls.NUM_QUESTION_LINES:
            raise ValueError(
                'Coordinate {j} does not correspond to a choice.'.format(j=j)
            )
        else:
            return (
                i * (curses.LINES - cls.NUM_QUESTION_LINES) +
                j - cls.NUM_QUESTION_LINES
            )

    def __call__(self, window):
        assert len(self.TAG) <= curses.COLS
        assert self.NUM_QUESTION_LINES <= curses.LINES
        page = 0
        min_page = 0
        max_page = (
            len(self.choices) // (curses.LINES - self.NUM_QUESTION_LINES)
        )
        max_page_max_y = self.NUM_QUESTION_LINES + (
            (len(self.choices) - 1) %
            (curses.LINES - self.NUM_QUESTION_LINES)
        )
        y = 0
        min_y = 0
        max_y = curses.LINES - 1 if page < max_page else max_page_max_y
        self.draw_page(window, page)
        while True:
            key = window.getch(0, curses.COLS - 1)
            if key == curses.KEY_DOWN:
                if y < max_y:
                    self.toggle(window, page, y)
                    y += 1
                    self.toggle(window, page, y)
                    min_y = self.NUM_QUESTION_LINES
                elif page < max_page:
                    self.emphasized[y] = False
                    page += 1
                    y = min_y
                    self.emphasized[y] = True
                    self.draw_page(window, page)
                    if page == max_page:
                        max_y = max_page_max_y
            elif key == curses.KEY_UP:
                if y > min_y:
                    self.toggle(window, page, y)
                    y -= 1
                    self.toggle(window, page, y)
                elif page > min_page:
                    max_y = curses.LINES - 1
                    self.emphasized[y] = False
                    page -= 1
                    y = max_y
                    self.emphasized[y] = True
                    self.draw_page(window, page)
            elif key == curses.KEY_ENTER:
                return self.choice_index(page, y)
        return None

    def draw_page(self, window, i):
        window.clear()
        self.draw_question(window)
        for j in range(1, curses.LINES):
            self.draw_choice(window, i, j)

    def draw_line(self, window, i, j):
        if j < self.NUM_QUESTION_LINES:
            self.draw_question(window)
        else:
            self.draw_choice(window, i, j)

    def attribute(self, j):
        return curses.A_STANDOUT if self.emphasized[j] else curses.A_NORMAL

    def draw_question(self, window):
        window.addstr(0, 0, self.question, self.attribute(0))

    def draw_choice(self, window, i, j):
        k = self.choice_index(i, j)
        if k < len(self.choices):
            window.addstr(j, 0, self.choices[k], self.attribute(j))

    def toggle(self, window, i, j):
        self.emphasized[j] = not self.emphasized[j]
        self.draw_line(window, i, j)
