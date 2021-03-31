##############################################################################
# (c) Crown copyright Met Office. All rights reserved.
# For further details please refer to the file COPYRIGHT
# which you should have received as part of this distribution
##############################################################################

import re
from pathlib import Path
from typing import \
    List, \
    Mapping, \
    Tuple, \
    Type, \
    Dict
from enum import Enum, auto
from multiprocessing.synchronize import Lock as LockT

from fab.artifact import \
    Artifact, \
    FileType, \
    State, \
    New, \
    Unknown, \
    Analysed, \
    Compiled, \
    Linked
from fab.tasks import Task
from fab.database import \
    SqliteStateDatabase, \
    FileInfoDatabase


class DiscoveryState(Enum):
    AWARE_OF = auto()
    SEEN = auto()
    COMPILED = auto()


class PathMap(object):
    def __init__(self,
                 pattern: str,
                 filetype: Type[FileType],
                 state: Type[State]):
        self._pattern = pattern
        self._compiled = re.compile(pattern)
        self._filetype = filetype
        self._state = state

    @property
    def pattern(self):
        return self._pattern

    @property
    def filetype(self):
        return self._filetype

    @property
    def state(self):
        return self._state

    def __contains__(self, path: Path) -> bool:
        matched = False
        if self._compiled.match(str(path)):
            matched = True
        return matched


class Engine(object):
    def __init__(self,
                 workspace: Path,
                 target: str,
                 pathmaps: List[PathMap],
                 taskmap: Mapping[
                     Tuple[Type[FileType], Type[State]],
                     Task]) -> None:
        self._workspace = workspace
        self._target = target
        self._pathmaps = pathmaps
        self._taskmap = taskmap
        self._database = SqliteStateDatabase(workspace)

    @property
    def target(self) -> str:
        return self._target

    def process(self,
                artifact: Artifact,
                discovery: Dict[str, DiscoveryState],
                objects: List[Artifact],
                lock: LockT) -> List[Artifact]:

        new_artifacts: List[Artifact] = []
        new_discovery: Dict[str, DiscoveryState] = {}
        new_objects: List[Artifact] = []
        # Identify tasks that are completely new
        if (artifact.state is New
                and artifact.filetype is Unknown):
            # Use the pathmap list to work out the
            # filetype and starting state
            new_artifact = None
            for pathmap in self._pathmaps:
                if artifact.location in pathmap:
                    new_artifact = Artifact(artifact.location,
                                            pathmap.filetype,
                                            pathmap.state)
            # Assuming we found a match and were able
            # to create the artifact, return it so that
            # it can be added to the queue
            if new_artifact is not None:
                # Also store its hash in the file database
                file_info = FileInfoDatabase(self._database)
                file_info.add_file_info(artifact.location,
                                        new_artifact.hash)
                new_artifacts.append(new_artifact)

        elif artifact.state is Analysed:

            # Work out whether this artifact needs to be
            # included in the build or not - if any of its
            # definitions are mentioned in the (shared)
            # discovery mapping, or if it is defining
            # the target of the build then it should be included

            # TODO: Looping through a list of what could
            # eventually contain every unit/symbol in the build has
            # the potential to become an issue for performance.
            # Longer term we probably want to drop using the shared
            # discovery array in favour of database lookups
            required = False
            for definition in artifact.defines:
                # Is this the target?
                if (definition == self.target
                        or definition in discovery):
                    required = True
                    break

            if required:
                # Update the discovery list to indicate that
                # the definitions from this Artifact are present
                # (but not yet compiled)
                for definition in artifact.defines:
                    if definition not in discovery:
                        new_discovery[definition] = DiscoveryState.SEEN

                # Now check whether the Artifact's dependencies
                # have already been seen and compiled
                compiled = [False]*len(artifact.depends_on)
                for idep, dependency in enumerate(artifact.depends_on):
                    # Only applies to str dependencies
                    if isinstance(dependency, Path):
                        continue
                    if dependency in discovery:
                        # Are the dependencies compiled?
                        if discovery[dependency] == DiscoveryState.COMPILED:
                            compiled[idep] = True
                    else:
                        # If the dependency isn't in the list at all yet
                        # then add an entry so the system knows we are
                        # expecting it later (for the above check)
                        new_discovery[dependency] = DiscoveryState.AWARE_OF

                # If the dependencies are satisfied (or there weren't
                # any) then this file can be compiled now
                if len(compiled) == 0 or all(compiled):
                    for definition in artifact.defines:
                        task = self._taskmap[(artifact.filetype,
                                              artifact.state)]
                        new_artifacts.extend(task.run([artifact]))
                        new_discovery[definition] = DiscoveryState.COMPILED
                else:
                    # If the dependencies weren't all satisfied then
                    # back on the queue for another pass later
                    new_artifacts.append(artifact)
            else:
                # If it wasn't required it could be later, so
                # put it back on the queue, unless the target
                # has been compiled, in which case it wasn't
                # needed at all!
                if (self._target not in discovery
                        or discovery[self._target] != DiscoveryState.COMPILED):
                    new_artifacts.append(artifact)

        elif artifact.state is Compiled:
            # Begin populating the list for linking; avoid adding the
            # same artifact locations to the list multiple times (artifacts
            # may appear twice in cases of Fortran-C Interoperability)
            if artifact.location not in [obj.location for obj in objects]:
                new_objects.append(artifact)
            # But do not return a new artifact - this object
            # is "done" as far as the processing is concerned

            # But, if this is the file containing the target
            # that means everything must have been compiled
            # by this point; so we can do the linking step
            if self._target in artifact.defines:
                task = self._taskmap[(artifact.filetype,
                                      artifact.state)]
                new_artifacts.extend(task.run(objects + [artifact]))

        elif artifact.state is Linked:
            # Nothing to do at present with the final linked
            # executable, but included here for completeness
            pass
        else:
            # If the object specifies any paths in its dependencies
            # then these must exist before it can be processed
            # TODO: This needs more thorough logic and to come from
            # the database eventually
            ready = True
            for dependency in artifact.depends_on:
                if isinstance(dependency, Path):
                    if not dependency.exists():
                        ready = False

            if ready:
                # An artifact with a filetype and state set
                # will have an appropriate task that should
                # be used to run it (though unlike the old
                # implementation this is probably returning
                # the instance of the Task not the class)
                if ((artifact.filetype, artifact.state)
                        in self._taskmap):
                    task = self._taskmap[(artifact.filetype,
                                          artifact.state)]

                    new_artifacts.extend(task.run([artifact]))
            else:
                new_artifacts.append(artifact)

        # Update shared arrays
        lock.acquire()
        objects.extend(new_objects)
        for key, value in new_discovery.items():
            discovery[key] = value
        lock.release()

        return new_artifacts
