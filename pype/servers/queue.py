#!/bin/env/python
# -*- encoding: utf-8 -*-
"""

"""
from __future__ import division, print_function

import time

import ray


class Queue(object):

    def __init__(self,
                 queue_type: str = 'fifo',
                 use_locking: bool = False,
                 use_semaphore: bool = True,
                 priority_first: bool = True,
                 semaphore: int = 10,
                 start_at_right: bool = True,
                 batch_lock: int = None,
                 max_size: int = -1):
        """

        :param use_locking:
        :param use_semaphore:
        :param semaphore:
        :param start_at_right:
        :param max_data_len:
        """
        if not isinstance(use_locking, bool):
            raise TypeError("use_locking arg must be boolean, not {}".format(
                type(use_locking).__name__))
        if not isinstance(use_semaphore, bool):
            raise TypeError("use_semaphore arg must be boolean, not {}".format(
                type(use_semaphore).__name__))
        if not isinstance(use_semaphore, int):
            raise TypeError("semaphore arg must be int, not {}".format(
                type(semaphore).__name__))
        if semaphore < 1:
            raise UserWarning("Semaphore must be > 0, not {}".format(
                semaphore))
        if use_semaphore and use_locking:
            raise UserWarning("Cannot have use_locking and use_semaphore")

        self._queue = []
        self.queue_type = queue_type
        self.use_locking = use_locking
        self.use_semaphore = use_semaphore
        self.semaphore = semaphore
        self.batch_lock = batch_lock
        self.priority_first = priority_first
        # TODO: Implement max data len
        self.max_size = max_size
        # TODO: Better variable name
        self.start_at_right = start_at_right
        if use_locking:
            self.push_locked = False
        self.active = True
        self.pull_average = 0
        self.pull_sum = 0
        self.pull_count = 0

    def is_active(self):
        return self.active

    def print_queue(self):
        """

        :return: None
        """
        print(self._queue)

    def queue_len(self) -> int:
        """

        :return:
        """
        return len(self._queue)

    @staticmethod
    def preprocess_val(val):
        """

        :param val:
        :return:
        """
        return val

    @staticmethod
    def postprocess_val(val):
        """

        :param val:
        :return:
        """
        return val

    def can_pull(self, batch_size: int = None) -> bool:
        """

        :param batch_size:
        :return:
        """
        if not (batch_size is None):
            if batch_size == -1:
                return len(self._queue) > 0
            return len(self._queue) >= batch_size
        return len(self._queue) > 0

    def can_push(self) -> bool:
        """

        :param self:
        :return:
        """
        if self.use_locking:
            return not self.push_locked
        elif self.use_semaphore:
            return self.semaphore > 0
        elif not (self.batch_lock is None):
            return len(self._queue) < self.batch_lock
        else:
            return True

    def push(self, data, index=0, expand=False, verify=False) -> None:
        """

        :param data:
        :param index:
        :param expand:
        :param verify:
        :return: None
        """
        if self.use_locking:
            self.push_locked = True
        if expand:
            if verify:
                if not isinstance(data, list):
                    raise TypeError(
                        "Input data should be type list with expand=True")
            data = list(map(self.preprocess_val, data))
            if self.start_at_right:
                self._queue = self._queue[:index] + data + self._queue[index:]
            else:
                self._queue = (self._queue[:index + len(
                    self._queue)] + data + self._queue[index + 1:])
        else:
            data = self.preprocess_val(data)
            self._queue.insert(index, data)


    def _single_batch_process(self, index, wrap, remove):
        output = self._queue[index:]
        if wrap:
            if not isinstance(output, list):
                output = [output]
        if remove:
            self._queue = self._queue[:index]
        return output

    # def _pull_verify(self, batch_size, index, wrap):
    #     if not isinstance(batch_size, int):
    #         raise TypeError("batch_size arg should be int, not: {}".format(
    #             type(batch_size).__name__))
    #     if (batch_size < -1) or (batch_size == 0):
    #         raise UserWarning(
    #             "batch_size should be -1 or > 0, not {}".format(
    #                 batch_size))
    #     if not isinstance(index, int):
    #         raise TypeError("index arg should be int, not: {}".format(
    #             type(index).__name__))
    #     if not isinstance(wrap, int):
    #         raise TypeError("wrap arg should be boolean, not: {}".format(
    #             type(wrap).__name__))
    #
    # def _single_batch_pull_verify(self, index, remove, wrap):
    #     self._pull_verify(batch_size=1, index=index, wrap=wrap)
    #     return self._single_batch_process(index, remove,wrap)
    #
    # def _single_batch_pull(self, index, remove, wrap):
    #     output = self._queue[index:]
    #     if wrap:
    #         if not isinstance(output, list):
    #             output = [output]
    #     if remove:
    #         self._queue = self._queue[:index]
    #     return output

    def pull(self,
             remove: bool = True,
             batch_size: int = 1,
             index: int = -1,
             wrap: bool = False,
             verify: bool = False,
             flip: bool = True):
        """

        :param remove:
        :param batch_size:
        :param index:
        :param wrap:
        :param verify:
        :return:
        """
        start_time = time.time()
        if verify:
            if not isinstance(batch_size, int):
                raise TypeError("batch_size arg should be int, not: {}".format(
                    type(batch_size).__name__))
            if (batch_size < -1) or (batch_size == 0):
                raise UserWarning(
                    "batch_size should be -1 or > 0, not {}".format(
                        batch_size))
            if not isinstance(index, int):
                raise TypeError("index arg should be int, not: {}".format(
                    type(index).__name__))
            if not isinstance(wrap, int):
                raise TypeError("wrap arg should be boolean, not: {}".format(
                    type(wrap).__name__))
        if self.use_locking:
            self.push_locked = False

        # Single batch size processing
        if batch_size == 1:
            if self.priority_first:
                output = self._queue[:1]
            else:
                output = self._queue[-1:]
            if wrap:
                output = [output]
            if remove:
                if self.priority_first:
                    self._queue = self._queue[1:]
                else:
                    self._queue = self._queue[:-1]
            return output

        # Full batch processing
        elif batch_size == -1:
            output = self._queue
            if remove:
                self._queue = []
            return output

        else:
            if self.queue_type == 'fifo':
                if self.priority_first:
                    output = self._queue[:batch_size]
                    if remove:
                        self._queue = self._queue[batch_size:]
                else:
                    output = self._queue[-batch_size:]
                    if remove:
                        self._queue = self._queue[:-batch_size]
            else:
                if self.priority_first:
                    output = self._queue[-batch_size:]
                    if remove:
                        self._queue = self._queue[:-batch_size]
                else:
                    output = self._queue[:batch_size]
                    if remove:
                        self._queue = self._queue[batch_size:]
            if wrap:
                if not isinstance(output, list):
                    output = [output]
        if flip:
            output.reverse()

        return output


@ray.remote
class RayQueue(Queue):

    def __init__(self,
                 use_locking: bool = False,
                 use_semaphore: bool = False,
                 batch_lock: int = None,
                 semaphore: int = 10):
        """

        :param use_locking:
        :param use_semaphore:
        :param semaphore:
        """
        super().__init__(use_locking=use_locking,
                         use_semaphore=use_semaphore,
                         batch_lock=batch_lock,
                         semaphore=semaphore)
