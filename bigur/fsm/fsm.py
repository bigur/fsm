'''Реализация конечного автомата.'''

__author__ = 'Gennady Kovalev <gik@bigur.ru>'
__copyright__ = '(c) 2016-2018 Business group for development management'
__licence__ = 'For license information see LICENSE'

from abc import ABCMeta
from asyncio import sleep, CancelledError
from enum import Enum
from inspect import iscoroutinefunction
from logging import getLogger
from typing import Callable, Dict

from bigur.rx import Subject, Observable, Observer


logger = getLogger('bigur.fsm')


class TransitionError(Exception):
    pass


class State(Enum):
    def __init__(self, code: str): # pylint: disable=unused-argument
        self.transitions: Dict[State, Callable] = {}


def on(event: str, state: State):
    def decorator(meth):
        meth.__fsm_event__ = (event, state)
        return meth
    return decorator


def transition(from_state: State, to_state: State):
    def decorator(meth):
        meth.__fsm_transition__ = (from_state, to_state)
        return meth
    return decorator


class ChangeStateObserver(Observer):
    '''Обработка события смены состояния объекта.'''
    def __init__(self, meth: Callable):
        self._meth = meth
        super().__init__()

    async def on_next(self, value: 'FSM'):
        try:
            await self._meth(value)
        except Exception as error: # pylint: disable=W0703
            logger.error('Ошибка при обработке события '
                         'смены состояния', exc_info=error)


class FSMMeta(ABCMeta):

    def __init__(cls, name, bases, attrs):

        if bases:
            states = attrs.get('states', getattr(cls, 'states', None))
            if not states:
                raise KeyError('необходимо определить состояния для FSM')

            initial = attrs.get('initial', getattr(cls, 'initial_state', None))
            if not initial:
                raise KeyError('необходимо определить начальное состояние '
                               'в классе {}'.format(name))

            for state in states:
                setattr(cls, 'on_enter_{}'.format(state.name), Subject())
                setattr(cls, 'on_exit_{}'.format(state.name), Subject())


            for meth in attrs.values():
                event_info = getattr(meth, '__fsm_event__', None)
                if event_info is not None:
                    if event_info[1] not in states:
                        raise KeyError('состояние {} не присутствует '
                                    'в классе {}'.format(event_info[1], cls))
                    event = getattr(cls, 'on_{}_{}'.format(event_info[0],
                                                        event_info[1].name))
                    # pylint: disable=W0212
                    event._observers.append(ChangeStateObserver(meth))

                transition_info = getattr(meth, '__fsm_transition__', None)
                if transition_info is not None:
                    transitions = transition_info[0].transitions
                    if transition_info[1] not in transitions:
                        transitions[transition_info[1]] = []
                    transitions[transition_info[1]].append(meth)

        super().__init__(name, bases, attrs)


class FSM(metaclass=FSMMeta):

    __multiple_path__ = False

    __metadata__ = {
        'replace_attrs': {'_state': 'state'},
        'picklers': {
            '_state': {
                'pickle': lambda self, value: value.name,
                'unpickle': lambda self, state, value: getattr(self.states, value)
            }
        }
    }

    states: State

    initial_state: State

    #: Задержка такта в цикле в секундах
    tick_time: int = 1

    def __init__(self):
        self._state: State = self.initial_state
        self._cancel: bool = False
        super().__init__()

    @property
    def state(self):
        return self._state

    def cancel(self):
        self._cancel = True

    async def change_state(self, state: State):
        logger.debug('Смена состояния %s: %s -> %s',
                     self, self._state.name, state.name)

        async def notify(observable: Observable):
            await observable.on_next(self)

        await notify(getattr(self, 'on_exit_{}'.format(self._state.name)))
        self._state = state
        await notify(getattr(self, 'on_enter_{}'.format(state.name)))

    async def _can_change(self, func: Callable):
        try:
            if iscoroutinefunction(func):
                return bool(await func(self))
            else:
                return bool(func(self))
        except Exception as error: # pylint: disable=W0703
            logger.warning('Ошибка при проверке возможности '
                           'смены состояния', exc_info=error)

    async def motor(self):
        '''Главный цикл конечного автомата. Запускается в
        :class:`asyncio.task.Task`, поэтому содержит обработку ошибок.'''
        logger.debug('Автомат %s запущен', self)

        while not getattr(self, '_cancel', False):
            try:
                next_states = []
                for next_state, funcs in self.state.transitions.items():
                    for func in funcs:
                        if await self._can_change(func):
                            next_states.append(next_state)
                            break
                if self.__multiple_path__ is False and len(next_states) > 1:
                    logger.error('Возможность сменить сразу на несколько '
                                 'состояний: %s', next_states)
                    raise TransitionError('возможность сменить сразу на '
                                          'несколько состояний')

                if len(next_states) > 0:
                    await self.change_state(next_states[0])

                await sleep(self.tick_time)

            except CancelledError:
                logger.debug('Получен сигнал завершения цикла автомата %s', self)
                break

        logger.debug('Автомат %s завершил работу', self)
