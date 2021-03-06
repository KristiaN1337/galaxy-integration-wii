import asyncio
import os
from subprocess import Popen
import sys
from shutil import copyfile
from xml.etree import ElementTree

import user_config
from backend import BackendClient
from galaxy.api.consts import LicenseType, LocalGameState, Platform
from galaxy.api.plugin import Plugin, create_and_run_plugin
from galaxy.api.types import Authentication, Game, LicenseInfo, LocalGame, GameTime
from version import __version__
import time

class DolphinPlugin(Plugin):

    def __init__(self, reader, writer, token):
        super().__init__(Platform.NintendoWii, __version__, reader, writer, token)
        self.backend_client = BackendClient()
        self.games = []
        if not os.path.exists(os.path.dirname(os.path.realpath(__file__)) + r'\gametimes.xml'):
            copyfile(os.path.dirname(os.path.realpath(__file__)) + r'\files\gametimes.xml', os.path.dirname(os.path.realpath(__file__)) + r'\gametimes.xml')
        self.game_times = self.get_the_game_times()
        self.local_games_cache = self.local_games_list()
        self.runningGame = self.runningGame = {"game_id": "", "starting_time": 0, "dolphin_running": None, "launched": False}

    async def authenticate(self, stored_credentials=None):
        return self.do_auth()

    def get_the_game_times(self):
        file = ElementTree.parse(os.path.dirname(os.path.realpath(__file__)) + r'\gametimes.xml')
        game_times = {}
        games_xml = file.getroot()
        for game in games_xml.iter('game'):
            game_id = str(game.find('id').text)
            tt = game.find('time').text
            ltp = game.find('lasttimeplayed').text
            game_times[game_id] = [tt, ltp]
        return game_times

    async def pass_login_credentials(self, step, credentials, cookies):
        return self.do_auth()

    def do_auth(self):
        user_data = {}
        username = user_config.roms_path
        user_data["username"] = username
        self.store_credentials(user_data)
        return Authentication("Dolphin", user_data["username"])

    async def launch_game(self, game_id):
        emu_path = user_config.emu_path
        for game in self.games:
            if game.id == game_id:
                if not user_config.retroarch:
                    openDolphin = Popen([emu_path, "-b", "-e", game.path])
                    gameStartingTime = time.time()
                    self.runningGame = {"game_id": game_id, "starting_time": gameStartingTime, "dolphin_running": openDolphin}
                else:
                    Popen([user_config.retroarch_executable, "-L", user_config.core_path + r'\dolphin_libretro.dll', game.path])
                break
        return

    async def install_game(self, game_id):
        pass

    async def uninstall_game(self, game_id):
        pass

    async def get_game_time(self, game_id, context=None):
        game_times = self.game_times
        game_time = int(game_times[game_id][0])
        game_time /= 60
        return GameTime(game_id, game_time, game_times[game_id][1])

    def local_games_list(self):
        local_games = []
        for game in self.games:
            local_games.append(
                LocalGame(
                    game.id,
                    LocalGameState.Installed
                )
            )
        return local_games

    def tick(self):

        async def update_local_games():
            loop = asyncio.get_running_loop()
            new_local_games_list = await loop.run_in_executor(None, self.local_games_list)
            notify_list = self.backend_client.get_state_changes(self.local_games_cache, new_local_games_list)
            self.local_games_cache = new_local_games_list
            for local_game_notify in notify_list:
                self.update_local_game_status(local_game_notify)

        file = ElementTree.parse(os.path.dirname(os.path.realpath(__file__)) + r'\gametimes.xml')
        if self.runningGame["dolphin_running"] is not None:
            if self.runningGame["dolphin_running"].poll() is None:
                self.runningGame["launched"] = True
            if self.runningGame["dolphin_running"].poll() is not None:
                if self.runningGame["launched"]:
                    current_time = round(time.time())
                    runtime = time.time() - self.runningGame["starting_time"]
                    games_xml = file.getroot()
                    for game in games_xml.iter('game'):
                        if str(game.find('id').text) == self.runningGame["game_id"]:
                            previous_time = int(game.find('time').text)
                            total_time = round(previous_time + runtime)
                            game.find('time').text = str(total_time)
                            game.find('lasttimeplayed').text = str(current_time)
                            self.update_game_time(
                                GameTime(self.runningGame["game_id"], int(total_time / 60), current_time))
                    file.write(os.path.dirname(os.path.realpath(__file__)) + r'\gametimes.xml')
                    self.runningGame["launched"] = False

        asyncio.create_task(update_local_games())

    async def get_owned_games(self):
        self.games = self.backend_client.get_games_db()
        owned_games = []

        for game in self.games:
            owned_games.append(
                Game(
                    game.id,
                    game.name,
                    None,
                    LicenseInfo(LicenseType.SinglePurchase, None)
                )
            )
        return owned_games

    async def get_local_games(self):
        return self.local_games_cache

    def shutdown(self):
        pass

def main():
    create_and_run_plugin(DolphinPlugin, sys.argv)

# run plugin event loop
if __name__ == "__main__":
    main()
