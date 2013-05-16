import sys
import os
import xdm
import git
from xdm.logger import *
from lib import requests

install_type_exe = 0# any compiled windows build
install_type_mac = 1# any compiled mac osx build
install_type_git = 2# running from source using git
install_type_source = 3# running from source without git
install_type_names = {install_type_exe: 'Windows Binary',
                   install_type_mac: 'Mac App',
                   install_type_git: 'Git',
                   install_type_source: 'Source'}


class CoreUpdater(object):

    def __init__(self):
        self.install_type = self._find_install_type()
        self.info = None

        if self.install_type == install_type_exe:
            self.updater = WindowsUpdateManager()
        if self.install_type == install_type_mac:
            self.updater = MacUpdateManager()
        elif self.install_type == install_type_git:
            self.updater = GitUpdateManager()
        elif self.install_type == install_type_source:
            self.updater = SourceUpdateManager()
        else:
            self.updater = None

    def _find_install_type(self):
        """Determines how this copy of XDM was installed."""
        if getattr(sys, 'frozen', None) == 'macosx_app': # check if we're a mac build
            install_type = 'osx'
        elif sys.platform == 'win32': # check if we're a windows build
            install_type = install_type_exe
        elif os.path.isdir(os.path.join(xdm.APP_PATH, '.git')):
            install_type = install_type_git
        else:
            install_type = install_type_source

        return install_type

    def check(self):
        """Checks the internet for a newer version.
        returns: UpdateManager.UpdateResponse()
        """
        log.info("Checking if %s needs an update" % install_type_names[self.install_type])
        self.info = self.updater.need_update()
        if not self.info.needUpdate:
            log.info(u"No update needed")

        return self.info


class UpdateResponse(object):
    def __init__(self):
        self._reset()

    def _reset(self):
        self.needUpdate = False
        self.localVersion = 0
        self.externalVersion = 0
        self.message = 'No update needed'
        self.extraData = {}

    def default(self):
        self._reset()
        return self

    def __str__(self):
        extra = '; '.join(self.extraData)
        return 'Needupdate: %s; current version: %s; external version: %s;\nExtra info: %s\n%s' % (self.needUpdate,
                                                                                                   self.localVersion,
                                                                                                   self.externalVersion,
                                                                                                   extra,
                                                                                                   self.message)


class UpdateManager(object):

    def __init__(self):
        self.response = UpdateResponse()

    def need_update(self):
        return self.response

    def update(self):
        return False


class BinaryUpdateManager(UpdateManager):
    pass


class WindowsUpdateManager(BinaryUpdateManager):
    pass


class MacUpdateManager(BinaryUpdateManager):
    pass


class SourceUpdateManager(object):
    pass


class GitUpdateManager(UpdateManager):

    #http://stackoverflow.com/questions/8290233/gitpython-get-list-of-remote-commits-not-yet-applied
    def need_update(self):
        repo = git.Repo(xdm.APP_PATH)                   # get the local repo
        local_commit = repo.commit()                    # latest local commit
        remote = git.remote.Remote(repo, 'origin')      # remote repo
        info = remote.fetch()[0]                        # fetch changes
        remote_commit = info.commit

        self.response.localVersion = local_commit.hexsha
        self.response.externalVersion = remote_commit.hexsha

        if repo.is_dirty():
            self.response.extraData['dirty_git'] = True
            msg = "Running on a dirty git installation! No real update check was done."
            log.warning(msg)
            self.response.message = msg
            return self.response

        behind = 0
        if local_commit.hexsha == remote_commit.hexsha: # local is updated; end
            self.response.message = 'No update needed'
            return self.response

        self.response.needUpdate = True
        for commit in self._repo_changes(remote_commit):
            if commit.hexsha == local_commit.hexsha:
                self.response.message = '%s commits behind.' % behind
                return self.response
            behind += 1
            if behind >= 10:
                self.response.message = 'Over 10 commits behind!'
                return self.response

    def _repo_changes(self, commit):
        "Iterator over repository changes starting with the given commit."
        next_parent = None
        yield commit                           # return the first commit itself
        while len(commit.parents) > 0:         # iterate
            for parent in commit.parents:        # go over all parents
                yield parent                       # return each parent
                next_parent = parent               # for the next iteration
            commit = next_parent                 # start again


class PluginUpdater(object):

    def __init__(self, pluginClass):
        self.response = UpdateResponse()
        self._plugin = pluginClass
        self._local_info = self._plugin.getMetaInfo()
        self.updater = None
        if self._local_info['format'] == 'zip':
            self.updater = ZipPluginDownloader()
        elif self._local_info['format'] == 'py':
            self.updater = PyPluginDownloader()

    def check(self):
        if self.updater is None:
            return self.response.default()

        """
        {'<plugin.identifier>': {'major_verion': 0,
                                 'minor_version': 2,
                                 'format': 'zip'/'py',
                                 'name': 'PlugiName',
                                 'desc': 'one line of information to the plugin',
                                 'update_url': '',
                                 'download_url: 'https://github.com/lad1337/XDM-plugin-de.lad1337.demopackage/archive/master.zip'}
        }
        """
        try:
            r = requests.get(self._local_info.update_url, timeout=20)
        except (requests.ConnectionError, requests.Timeout):
            log.error("Error while retrieving the update for %s" % self._plugin.__class__.__name__)
            return self.response.default()
        json = r.json()
        local_version = float(self._plugin.version)
        external_version = float('%s.%s' % (json['major'], json['major']))
        if local_version <= external_version:
            return self.response
        msg = '%s needs an update. local version: %s external version: %s' % (self._plugin, local_version, external_version)
        log.info(msg)
        self.response.message = msg
        self.response.needUpdate = True
        self.response.localVersion = local_version
        self.response.externalVersion = external_version


class ZipPluginDownloader(object):

    def download(self, info):
        try:
            r = requests.get(info["download_url"], timeout=20)
        except (requests.ConnectionError, requests.Timeout):
            log.error("Error while downloading %s" % info['identifier'])
        return False


class PyPluginDownloader(object):

    def download(self, info):
        try:
            r = requests.get(info["download_url"], timeout=20)
        except (requests.ConnectionError, requests.Timeout):
            log.error("Error while downloading %s" % info['identifier'])
        return False
