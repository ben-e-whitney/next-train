"""
curses tool to allow a user to select from a list of options.
"""

import curses
curses.KEY_ENTER = 10
import itertools
import typing

class Chooser:
    """
    Chooser between a list of options.

    Parameters
    ----------
    question
        Question whose answer should be one of `choices`.
    choices
        Possible answers to `question`.
    """

    CHOICE_INDENTATION: int = 2
    NUM_QUESTION_LINES: int = 1
    TAG: str = ' ...'

    class _EmphasisTranslator:
        """
        Translator from emphasis flags to `curses` attributes.

        Parameters
        ----------
        emphasized
            Emphasis flags to be translated.
        """

        def __init__(self, emphasized: typing.List[bool]) -> None:
            """
            Initialize this _EmphasisTranslator.
            """

            self.emphasized: typing.List[bool] = emphasized

        def __getitem__(self, j: int) -> int:
            """
            Translate an emphasis flag to a `curses` attribute.

            Parameters
            ----------
            j
                Line index (`y` coordinate of the line).

            Returns
            -------
            int
                Current attribute for the line.
            """

            return curses.A_STANDOUT if self.emphasized[j] else curses.A_NORMAL

    def __init__(self, question: str, choices: typing.Collection[str]) -> None:
        """
        Initialize this Chooser.
        """

        self.question: str = self.truncate(question)
        pattern: str = ' ' * self.CHOICE_INDENTATION + (
            '[{{:>{wid}}}] {{}}'.format(wid=len(str(len(choices) - 1)))
        )
        self.choices: typing.Tuple[str, ...] = tuple(map(
            self.truncate,
            itertools.starmap(pattern.format, enumerate(choices))
        ))
        self.emphasized: typing.List[bool] = list(
            itertools.repeat(False, curses.LINES)
        )
        self.emphasized[0] = True
        self.attributes: Chooser._EmphasisTranslator = (
            self._EmphasisTranslator(self.emphasized)
        )

    @classmethod
    def truncate(cls, line: str) -> str:
        """
        Truncate a line so it fits on the screen.

        Parameters
        ----------
        line
            Untruncated line of text to be displayed.

        Returns
        -------
        str
            Truncated line.
        """

        return (
            line if len(line) <= curses.COLS
            else line[: curses.COLS - len(cls.TAG)] + cls.TAG
        )

    @classmethod
    def choice_index(cls, i: int, j: int) -> int:
        """
        Compute the index of a choice displayed on the screen.

        Parameters
        ----------
        i
            Page index.
        j
            Line index (`y` coordinate of the line).

        Returns
        -------
        int
            Index of choice displayed on line `j` of page `i`.
        """

        if j < cls.NUM_QUESTION_LINES:
            raise ValueError(
                'Coordinate {j} does not correspond to a choice.'.format(j=j)
            )
        else:
            return (
                i * (curses.LINES - cls.NUM_QUESTION_LINES) +
                j - cls.NUM_QUESTION_LINES
            )

    def __call__(self, window) -> int:
        """
        Display question and choices to user and obtain response.

        Parameters
        ----------
        window : curses.Window
            Window on which to display choices to user.

        Returns
        -------
        int
            Index of choice made by user.
        """

        assert len(self.TAG) <= curses.COLS
        assert self.NUM_QUESTION_LINES <= curses.LINES
        page: int = 0
        min_page: int = 0
        assert len(self.choices) > 0
        max_page: int = (
            (len(self.choices) - 1) // (curses.LINES - self.NUM_QUESTION_LINES)
        )
        max_page_max_y: int = self.NUM_QUESTION_LINES + (
            (len(self.choices) - 1) %
            (curses.LINES - self.NUM_QUESTION_LINES)
        )
        y: int = 0
        min_y: int = 0
        max_y: int = curses.LINES - 1 if page < max_page else max_page_max_y
        self.draw_page(window, page)
        digits: typing.List[int] = []
        move_made: bool = False
        while True:
            key: int = window.getch(0, curses.COLS - 1)
            if key == curses.KEY_DOWN:
                digits.clear()
                if y < max_y:
                    self.toggle(window, page, y)
                    y += 1
                    self.toggle(window, page, y)
                    if not move_made:
                        min_y = self.NUM_QUESTION_LINES
                        move_made = True
                elif page < max_page:
                    self.emphasized[y] = False
                    page += 1
                    y = min_y
                    self.emphasized[y] = True
                    self.draw_page(window, page)
                    if page == max_page:
                        max_y = max_page_max_y
            elif key == curses.KEY_UP:
                digits.clear()
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
                if digits:
                    index = 0
                    for digit in digits:
                        index *= 10
                        index += digit
                    if index < len(self.choices):
                        return index
                    else:
                        digits.clear()
                if move_made:
                    return self.choice_index(page, y)
            else:
                char = chr(key)
                if char.isdigit():
                    digits.append(int(char))
                else:
                    digits.clear()

    def draw_page(self, window, i: int) -> None:
        """
        Draw a page on a window.

        Parameters
        ----------
        window : curses.Window
            Window on which to draw the page.
        i
            Page index.
        """

        window.clear()
        self.draw_question(window)
        for j in range(1, curses.LINES):
            self.draw_choice(window, i, j)

    def draw_line(self, window, i: int, j: int) -> None:
        """
        Draw a line of a page on a window.

        Parameters
        ----------
        window : curses.Window
            Window on which to draw the page.
        i
            Page index.
        j
            Line index (`y` coordinate of the line).
        """

        if j < self.NUM_QUESTION_LINES:
            self.draw_question(window)
        else:
            self.draw_choice(window, i, j)

    def draw_question(self, window) -> None:
        """
        Draw the question on a window.

        Parameters
        ----------
        window : curses.Window
            Window on which to draw the question.
        """

        window.addstr(0, 0, self.question, self.attributes[0])

    def draw_choice(self, window, i: int, j: int) -> None:
        """
        Draw a choice on a window.

        Parameters
        ----------
        window : curses.Window
            Window on which to draw the choice.
        i
            Page index.
        j
            Line index (`y` coordinate of the line).
        """

        k: int = self.choice_index(i, j)
        if k < len(self.choices):
            window.addstr(j, 0, self.choices[k], self.attributes[j])

    def toggle(self, window, i: int, j: int) -> None:
        """
        Toggle the emphasis state of a line.

        Parameters
        ----------
        window : curses.Window
            Window on which to toggle the line.
        i
            Page index.
        j
            Line index (`y` coordinate of the line).
        """

        self.emphasized[j] = not self.emphasized[j]
        self.draw_line(window, i, j)
