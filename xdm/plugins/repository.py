
from xdm.logger import *
from lib import requests
import datetime
from xdm.plugins.bases import __all__ as allClasses
import time
from xdm import common, helper

from lib import requests
import zipfile, StringIO
import xdm
import os


class RepoManager(object):

    def __init__(self, repos):
        self._repos = repos
        self.repos = []
        for repo in repos:
            self.repos.append(Repo(repo.name, repo.url))
        self.cached = False
        self.caching = False
        self.last_cache = None
        self.updateable_plugins = {}

    def cache(self):
        self.caching = True
        for repo in self.repos:
            try:
                repo.cache()
            except:
                log.error('%s had an error during cache' % repo)
            for r in self._repos:
                if r.url == repo.url:
                    if r.name != repo.name:
                        r.name = repo.name
                        r.save()
        self.last_cache = datetime.datetime.now()
        self.cached = True
        self.caching = False
        self.install_messages = []

    def getRepos(self):
        return self.repos

    def checkForUpdate(self, plugins):
        updateable_plugins = {}
        for plugin in plugins:
            if plugin.identifier:
                for repo in self.repos:
                    for repo_plugin in repo.getPlugins():
                        if repo_plugin.identifier == plugin.identifier and self._updateable(repo_plugin, plugin):
                            updateable_plugins[plugin.identifier] = (repo_plugin, plugin)
        log.info('%s Plugins have an update' % len(updateable_plugins))
        self.updateable_plugins = updateable_plugins

    def hasUpdate(self, identifier):
        if identifier in self.updateable_plugins:
            return self.updateable_plugins[identifier][0].versionHuman()
        return ''

    def _updateable(self, repo_plugin, plugin):
        if repo_plugin.major_version > plugin.major_version:
            return True
        elif repo_plugin.major_version == plugin.major_version and repo_plugin.minor_version > plugin.minor_version:
            return True
        return False

    def isInstalled(self, identifier):
        return identifier in self.updateable_plugins

    def _prepareIntall(self):
        self._read_messages = []
        helper.cleanTempFolder()

    def install(self, identifier):
        self.install_messages = [('info', 'install.py -i %s' % identifier)]
        self.setNewMessage('info', 'Getting download URL')

        plugin_to_update = None
        for repo in self.repos:
            for repo_plugin in repo.getPlugins():
                if repo_plugin.identifier == identifier:
                    plugin_to_update = repo_plugin

        if plugin_to_update is None:
            self.setNewMessage('error', 'Could not find a plugin with identifier %s' % identifier)
            self.setNewMessage('Done!')
            return

        self.setNewMessage('info', 'Installing %s(%s)' % (plugin_to_update.name, plugin_to_update.versionHuman()))

        for plugin in common.PM.getAll(returnAll=True, instance='Default'):
            if plugin.identifier == plugin_to_update.identifier:
                if self._updateable(repo_plugin, plugin_to_update):
                    self.setNewMessage('error', '%s is already installed and does not need an update' % plugin_to_update.name)
                    self.setNewMessage('info', 'Done!')
                    return
                else:
                    self.setNewMessage('info', '%s is already installed but has an update' % plugin_to_update.name)
                    break
        else:
            self.setNewMessage('info', '%s is not yet installed' % plugin_to_update)

        if repo_plugin.format == 'zip':
            downloader = ZipPluginInstaller()
        else:
            self.setNewMessage('error', 'Format %s is not supported. sorry' % plugin_to_update.format)
            self.setNewMessage('info', 'Done!')
            return

        install_path = xdm.PLUGININSTALLPATH
        extra_plugin_path = common.SYSTEM.c.extra_plugin_path
        if extra_plugin_path and os.path.isdir(extra_plugin_path):
            install_path = extra_plugin_path
        self.setNewMessage('info', 'Installing into %s' % install_path)
        self.setNewMessage('info', 'Starting download. please wait...' % plugin_to_update)
        self.setNewMessage('info', plugin_to_update.download_url, install_path)
        if downloader.install(self, plugin_to_update):
            self.setNewMessage('info', 'Instalation successful')
            self.setNewMessage('info', 'Recaching plugins')
        else:
            self.setNewMessage('error', 'Instalation unsuccessful')

        self.setNewMessage('info', 'Done!')

    def getLastInstallMessages(self):
        out = []
        for index, message in enumerate(self.install_messages):
            if not index in self._read_messages:
                out.append(message)
                self._read_messages.append(index)
        return out

    def setNewMessage(self, lvl, msg):
        self.install_messages.append((lvl, msg))


class ZipPluginInstaller():

    def install(self, manager, repo_plugin, install_path=''):
        r = requests.get(repo_plugin.download_url)
        manager.setNewMessage('info', 'Download done.')
        z = zipfile.ZipFile(StringIO.StringIO(r.content))
        z.extractall(xdm.TEMPPATH)
        manager.setNewMessage('info', 'Extration done.')
        for root, dirs, files in os.walk(xdm.TEMPPATH):
            for cur_dir in dirs:
                if cur_dir == repo_plugin.name:
                    manager.setNewMessage('info', 'Found extracted plugin folder.')
                    manager.setNewMessage('info', os.path.join(root, cur_dir))
        
                

class Repo(object):

    def __init__(self, name, url):
        self.name = name
        self.url = url
        self.plugins = []

    def getPlugins(self):
        return self.plugins

    def __str__(self):
        return '%s %s' % (self.name, self.url)

    def cache(self):
        """Checks the internet for plusings in repo"""
        self.plugins = []
        log.info("Checking if repo at %s" % self.url)
        try:
            r = requests.get(self.url, timeout=20)
        except (requests.ConnectionError, requests.Timeout):
            log.error("Error while retrieving repo information from %s" % self.url)
            return
        repo_info = r.json()
        repo_name = repo_info['name']
        self.name = repo_name
        for identifier, plugin_versions in repo_info['plugins'].items():
            for version_info in plugin_versions:
                self.plugins.append(ExternalPlugin(identifier, version_info))


class RepoPlugin(object):
    def __init__(self, identifier, info):
        self.major_version = info['major_version']
        self.minor_version = info['minor_version']
        self.format = info['format']
        self.name = info['name']
        self.desc = info['desc']
        self.update_url = info['update_url']
        self.download_url = info['download_url']
        print 'download_url', self.download_url
        self.type = info['type']
        self.identifier = identifier

    def checkType(self):
        return self.type in allClasses

    def versionHuman(self):
        return '%s.%s' % (self.major_version, self.minor_version)

    def __str__(self):
        return'Name: %s, identifier: %s, download_url: %s, desc: %s' % (self.name, self.identifier, self.download_url, self.desc)


class LocalPlugin(RepoPlugin):

    def __init__(self, identifier, info):
        self.local = True
        super(LocalPlugin, self).__init__(identifier, info)


class ExternalPlugin(RepoPlugin):

    def __init__(self, identifier, info):
        self.local = False
        super(ExternalPlugin, self).__init__(identifier, info)