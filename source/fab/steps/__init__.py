import multiprocessing


# We sometimes need to turn multiprocessing off when debugging a build.
from multiprocessing import cpu_count
from typing import Dict


class Step(object):
    """
    Base class for build steps.

    Provides multiprocessing capabilities.

    """

    workspace = None
    use_multiprocessing = True
    n_procs = max(1, cpu_count() - 1)
    debug_skip = False

    def __init__(self, name):
        self.name = name

    def run(self, artefacts: Dict):
        """
        Process some input artefacts and add some output artefacts. Defined by the subclass.

        Args:
            - artefacts: Build artefacts created by previous Steps, to which we add our new artefacts.

        """
        raise NotImplementedError

    def run_mp(self, items, func):
        """
        Like run(), but uses multiprocessing to process multiple items at once.

        """
        if self.use_multiprocessing:
            with multiprocessing.Pool(self.n_procs) as p:
                results = p.map(func, items)
        else:
            results = [func(f) for f in items]

        return results

    def run_mp_imap(self, items, func, result_handler):
        """
        Like run_mp, but uses imap instead of map so that we can process each result as it happens.

        This is useful, for example, for a time consuming process where we want to save our progress as we go
        instead of waiting for everything to finish, allowing us to pick up where we left off in the program is halted.

        """
        if self.use_multiprocessing:
            with multiprocessing.Pool(self.n_procs) as p:
                # We use imap because we want to save progress as we go
                analysis_results = p.imap_unordered(func, items)
                result_handler(analysis_results)
        else:
            analysis_results = (func(a) for a in items)  # generator
            result_handler(analysis_results)