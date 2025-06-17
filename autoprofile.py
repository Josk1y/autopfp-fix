import asyncio
import ast
import time
import logging
from io import BytesIO
from telethon.tl import functions
from .. import loader, utils
from PIL import Image

logger = logging.getLogger(__name__)

try:
    from PIL import Image
except ImportError:
    pil_installed = False
else:
    pil_installed = True


@loader.tds
class AutoProfileMod(loader.Module):
    """Automatic stuff for your profile :P"""
    strings = {
        "name": "Automatic Profile",
        "missing_pil": "<b>You don't have Pillow installed</b>",
        "missing_pfp": "<b>You don't have a profile picture to rotate</b>",
        "invalid_args": "<b>Missing parameters, please read the docs</b>",
        "invalid_degrees": "<b>Invalid number of degrees to rotate, please read the docs</b>",
        "invalid_delete": "<b>Please specify whether to delete the old pictures or not</b>",
        "enabled_pfp": "<b>Enabled profile picture rotation</b>",
        "pfp_not_enabled": "<b>Profile picture rotation is not enabled</b>",
        "pfp_disabled": "<b>Profile picture rotation disabled</b>",
        "missing_time": "<b>Time was not specified in bio</b>",
        "enabled_bio": "<b>Enabled bio clock</b>",
        "bio_not_enabled": "<b>Bio clock is not enabled</b>",
        "disabled_bio": "<b>Disabled bio clock</b>",
        "enabled_name": "<b>Enabled name clock</b>",
        "name_not_enabled": "<b>Name clock is not enabled</b>",
        "disabled_name": "<b>Name clock disabled</b>",
        "how_many_pfps": "<b>Please specify how many profile pictures should be removed</b>",
        "invalid_pfp_count": "<b>Invalid number of profile pictures to remove</b>",
        "removed_pfps": "<b>Removed {} profile pic(s)</b>"
    }

    def __init__(self):
        self.bio_enabled = False
        self.name_enabled = False
        self.pfp_enabled = False
        self.raw_bio = None
        self.raw_name = None

    async def client_ready(self, client, db):
        self.client = client

    async def validate_image(self, photo_bytes):
        """Validate and fix image if needed"""
        try:
            photo_bytes.seek(0)
            img = Image.open(photo_bytes)
            img.verify()
            photo_bytes.seek(0)
            return Image.open(photo_bytes)
        except Exception as e:
            logger.error(f"Image validation failed: {e}")
            raise

    async def autopfpcmd(self, message):
        """Rotate profile picture. Usage: .autopfp <degrees> <True/False>"""
        if not pil_installed:
            return await utils.answer(message, self.strings["missing_pil"])

        args = utils.get_args(message)
        if len(args) != 2:
            return await utils.answer(message, self.strings["invalid_args"])

        try:
            degrees = int(args[0])
            delete_previous = ast.literal_eval(args[1])
            if not isinstance(delete_previous, bool):
                return await utils.answer(message, self.strings["invalid_delete"])
        except (ValueError, SyntaxError):
            return await utils.answer(message, self.strings["invalid_degrees"])

        try:
            photos = await self.client.get_profile_photos("me", limit=1)
            if not photos:
                return await utils.answer(message, self.strings["missing_pfp"])

            with BytesIO() as pfp_bytes:
                await self.client.download_profile_photo("me", file=pfp_bytes)
                if not pfp_bytes.getvalue():
                    return await utils.answer(message, self.strings["missing_pfp"])

                try:
                    raw_pfp = await self.validate_image(pfp_bytes)
                except Exception:
                    return await utils.answer(message, self.strings["image_error"])

                self.pfp_enabled = True
                await utils.answer(message, self.strings["enabled_pfp"])

                async def rotation_loop():
                    pfp_degree = 0
                    while self.pfp_enabled:
                        try:
                            pfp_degree = (pfp_degree + degrees) % 360
                            rotated = raw_pfp.rotate(pfp_degree, expand=True)
                            
                            with BytesIO() as buf:
                                rotated.save(buf, format="PNG", quality=95)
                                buf.seek(0)
                                
                                if delete_previous:
                                    await self.client(functions.photos.DeletePhotosRequest(
                                        await self.client.get_profile_photos("me", limit=1)
                                    ))
                                
                                await self.client(functions.photos.UploadProfilePhotoRequest(
                                    file=await self.client.upload_file(buf)
                                ))
                            
                            await asyncio.sleep(10)  # 10 seconds interval
                        except Exception as e:
                            logger.error(f"Rotation error: {e}")
                            await asyncio.sleep(30)

                self.rotation_task = asyncio.create_task(rotation_loop())

        except Exception as e:
            logger.exception("Autopfp error")
            return await utils.answer(message, f"<b>Error:</b> {str(e)}")

    async def stopautopfpcmd(self, message):
        """Stop profile rotation"""
        if not self.pfp_enabled:
            return await utils.answer(message, self.strings["pfp_not_enabled"])
        
        self.pfp_enabled = False
        if self.rotation_task:
            self.rotation_task.cancel()
            try:
                await self.rotation_task
            except asyncio.CancelledError:
                pass
        
        await utils.answer(message, self.strings["pfp_disabled"])

    async def autobiocmd(self, message):
        """Automatically changes your account's bio with current time, usage:
            .autobio '<message, time as {time}>'"""

        msg = utils.get_args(message)
        if len(msg) != 1:
            return await utils.answer(message, self.strings("invalid_args", message))
        raw_bio = msg[0]
        if "{time}" not in raw_bio:
            return await utils.answer(message, self.strings("missing_time", message))

        self.bio_enabled = True
        self.raw_bio = raw_bio
        await self.allmodules.log("start_autobio")
        await utils.answer(message, self.strings("enabled_bio", message))

        while self.bio_enabled is True:
            current_time = time.strftime("%H:%M")
            bio = raw_bio.format(time=current_time)
            await self.client(functions.account.UpdateProfileRequest(
                about=bio
            ))
            await asyncio.sleep(60)

    async def stopautobiocmd(self, message):
        """Stop autobio cmd."""

        if self.bio_enabled is False:
            return await utils.answer(message, self.strings("bio_not_enabled", message))
        else:
            self.bio_enabled = False
            await self.allmodules.log("stop_autobio")
            await utils.answer(message, self.strings("disabled_bio", message))
            await self.client(functions.account.UpdateProfileRequest(about=self.raw_bio.format(time="")))

    async def autonamecmd(self, message):
        """Automatically changes your Telegram name with current time, usage:
            .autoname '<message, time as {time}>'"""

        msg = utils.get_args(message)
        if len(msg) != 1:
            return await utils.answer(message, self.strings("invalid_args", message))
        raw_name = msg[0]
        if "{time}" not in raw_name:
            return await utils.answer(message, self.strings("missing_time", message))

        self.name_enabled = True
        self.raw_name = raw_name
        await self.allmodules.log("start_autoname")
        await utils.answer(message, self.strings("enabled_name", message))

        while self.name_enabled is True:
            current_time = time.strftime("%H:%M")
            name = raw_name.format(time=current_time)
            await self.client(functions.account.UpdateProfileRequest(
                first_name=name
            ))
            await asyncio.sleep(60)

    async def stopautonamecmd(self, message):
        """Stop autoname cmd."""

        if self.name_enabled is False:
            return await utils.answer(message, self.strings("name_not_enabled", message))
        else:
            self.name_enabled = False
            await self.allmodules.log("stop_autoname")
            await utils.answer(message, self.strings("disabled_name", message))
            await self.client(functions.account.UpdateProfileRequest(
                first_name=self.raw_name.format(time="")
            ))

    async def delpfpcmd(self, message):
        """Remove x profile pic(s) from your profile.
        .delpfp <pfps count/unlimited - remove all>"""

        args = utils.get_args(message)
        if not args:
            return await utils.answer(message, self.strings("how_many_pfps", message))
        try:
            pfps_count = int(args[0])
        except ValueError:
            return await utils.answer(message, self.strings("invalid_pfp_count", message))
        if pfps_count < 0:
            return await utils.answer(message, self.strings("invalid_pfp_count", message))
        if pfps_count == 0:
            pfps_count = None

        to_delete = await self.client.get_profile_photos("me", limit=pfps_count)
        await self.client(functions.photos.DeletePhotosRequest(to_delete))

        await self.allmodules.log("delpfp")
        await utils.answer(message, self.strings("removed_pfps", message).format(len(to_delete)))
        return await utils.answer(message, self.strings("how_many_pfps", message))
