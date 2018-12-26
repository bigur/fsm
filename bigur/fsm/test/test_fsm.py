__author__ = 'Gennady Kovalev <gik@bigur.ru>'
__copyright__ = '(c) 2016-2018 Business group for development management'
__licence__ = 'For license information see LICENSE'

from pytest import fixture, mark

from bigur.fsm import FSM, State


class TestFSM(object):
    '''Тестирование конечного автомата'''
    @mark.asyncio
    async def test_definition(self):
        '''Объявление конечного автомата'''
        class DocumentState(State):
            created = 'created'

        class Document(FSM):
            states = DocumentState
            initial_state = DocumentState.created

        doc = Document()
        assert doc.state == DocumentState.created
