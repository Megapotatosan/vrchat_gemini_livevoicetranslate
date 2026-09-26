# The webrtcvad module is installed by the "webrtcvad-wheels" distribution; the stock hook looks for "webrtcvad".
from PyInstaller.utils.hooks import copy_metadata

datas = copy_metadata("webrtcvad-wheels")
