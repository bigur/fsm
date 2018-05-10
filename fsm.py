'''Реализация конечного автомата.'''

__author__ = 'Gennady Kovalev <gik@bigur.ru>'
__copyright__ = '(c) 2016-2018 Business group for development management'
__licence__ = 'For license information see LICENSE'

from enum import Enum
from asyncio import sleep, CancelledError
from inspect import iscoroutinefunction
from logging import getLogger

from bigur.rx import Subject, Observer
from bigur.store.stored import MetadataType


logger = getLogger('bigur.fsm')


class TransitionError(Exception):
    pass


def on(event, state):
    def decorator(meth):
        meth.__fsm_event__ = (event, state)
        return meth
    return decorator


def transition(from_state, to_state):
    def decorator(meth):
        meth.__fsm_transition__ = (from_state, to_state)
        return meth
    return decorator


class States(Enum):
    def __init__(self, code):
        self.transitions = {}


class ChangeStateObserver(Observer):
    '''Обработка события смены состояния объекта.'''
    def __init__(self, meth):
        self._meth = meth
        super().__init__()

    async def on_next(self, value):
        try:
            await self._meth(value)
        except Exception as error: # pylint: disable=W0703
            await self.on_error(error)

    async def on_error(self, error):
        logger.error('Ошибка при обработке события '
                     'смены состояния', exc_info=error)


class FSMMeta(type):

    def __init__(cls, name, bases, attrs):
        states = attrs.get('states', cls.states)

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


class StoredFSMMeta(MetadataType, FSMMeta):
    '''Объединение метаклассов от stored и fsm.'''
    def __init__(cls, name, bases, attrs):
        MetadataType.__init__(cls, name, bases, attrs)
        FSMMeta.__init__(cls, name, bases, attrs)


class FiniteStateMachine(metaclass=FSMMeta):

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

    states = States

    initial_state = None

    #: Задержка такта в цикле в секундах
    tick_time = 1

    def __init__(self):
        # Устанавливаем начальное состояние
        assert self.initial_state is not None, \
                'установите начальное состояние для {}'.format(self)
        self._state = self.initial_state
        self._sleep = False
        super().__init__()

    @property
    def state(self):
        return self._state

    def cancel(self):
        self._cancel = True

    async def change_state(self, state):
        logger.debug('Смена состояния %s: %s -> %s', self, self._state.name, state.name)

        async def notify(observable):
            await observable.on_next(self)

        await notify(getattr(self, 'on_exit_{}'.format(self._state.name)))
        self._state = state
        await notify(getattr(self, 'on_enter_{}'.format(state.name)))

    async def _can_change(self, func):
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
