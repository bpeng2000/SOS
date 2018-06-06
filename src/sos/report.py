#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import os
import time
import base64
from collections import defaultdict
from contextlib import contextmanager

from .utils import TimeoutInterProcessLock, env, format_duration, dot_to_gif


@contextmanager
def workflow_report(mode='a'):
    workflow_sig = os.path.join(
        env.exec_dir, '.sos', f'{env.config["master_id"]}.sig')
    with TimeoutInterProcessLock(workflow_sig + '_'):
        with open(workflow_sig, mode) as sig:
            yield sig


class WorkflowSig(object):
    def __init__(self, workflow_info):
        self.data = defaultdict(lambda: defaultdict(list))
        with open(workflow_info, 'r') as wi:
            for line in wi:
                try:
                    entry_type, id, item = line.split('\t', 2)
                    self.data[entry_type][id].append(item.strip())
                except Exception as e:
                    env.logger.debug(f'Failed to read report line {line}: {e}')

    def convert_time(self, info):
        if 'start_time' in info:
            info['start_time_str'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(info['start_time']))
        if 'end_time' in info:
            info['end_time_str'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(info['end_time']))
        if 'start_time' in info and 'end_time' in info:
            info['duration'] = int(info['end_time'] - info['start_time'])
            info['duration_str'] = format_duration(info['duration'])

    def workflows(self):
        try:
            # workflows has format
            #workflow  workflow_id dict1
            #workflow  workflow_id dict2
            #workflow  workflow_id2 dict1
            workflows = defaultdict(dict)
            for id, values in self.data['workflow'].items():
                for val in values:
                    workflows[id].update(eval(val))
            for k, v in workflows.items():
                self.convert_time(v)
                if 'dag' in v:
                    try:
                        v['dag_img'] = dot_to_gif(v['dag'], warn=env.logger.warning)
                    except Exception as e:
                        env.logger.warning(f'Failed to obtain convert dag to image: {e}')
            return workflows
        except Exception as e:
            env.logger.warning(f'Failed to obtain workflow information: {e}')
            return {}

    def tasks(self):
        try:
            # there should be only one task for each id
            tasks = {id: eval(res[0]) for id, res in self.data['task'].items()}
            for key, val in tasks.items():
                self.convert_time(val)
                if 'peak_cpu' in val:
                    val['peak_cpu_str'] = f'{val["peak_cpu"]:.1f}%'
                if 'peak_mem' in val:
                    val['peak_mem_str'] = f'{val["peak_mem"] / 1024 / 1024 :.1f}Mb'
            return tasks
        except:
            return {}

    def steps(self):
        try:
            all_steps = [eval(x) for x in sum(self.data['step'].values(), [])]
            for step in all_steps:
                self.convert_time(step)
            return all_steps
        except:
            return {}

    def tracked_files(self):
        try:
            files = sum(self.data['input_file'].values(), []) + sum(
                self.data['output_file'].values(), []) + sum(self.data['dependent_file'].values(), [])
            return [eval(x) for x in files]
        except:
            return []


def render_report(output_file, workflow_id):
    data = WorkflowSig(os.path.join(
        env.exec_dir, '.sos', f'{workflow_id}.sig'))

    from jinja2 import Environment, PackageLoader, select_autoescape
    template = Environment(
        loader=PackageLoader('sos', 'templates'),
        autoescape=select_autoescape(['html', 'xml'])
    ).get_template('workflow_report.tpl')

    context = {
        'workflows': data.workflows(),
        'tasks': data.tasks(),
        'steps': data.steps(),
    }
    # derived context
    context['master_id'] = next(iter(context['workflows'].values()))['master_id']
    context['subworkflows'] = [x for x in context['workflows'].keys() if x != context['master_id']]
    with open(output_file, 'w') as wo:
        wo.write(template.render(context))
    env.logger.info(f'Summary of workflow saved to {output_file}')
