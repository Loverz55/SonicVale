from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from typing import List, Tuple

from sqlalchemy import Sequence

from app.core.audio_engin import AudioProcessor
from app.dto.voice_dto import VoiceAudioProcessDTO
from app.entity.voice_entity import VoiceEntity
from app.models.po import VoicePO
from app.repositories.multi_emotion_voice_repository import MultiEmotionVoiceRepository
from app.repositories.voice_repository import VoiceRepository


class VoiceService:

    def __init__(self, repository: VoiceRepository,multi_emotion_voice_repository: MultiEmotionVoiceRepository):
        """注入 repository"""
        self.repository = repository
        self.multi_emotion_voice_repository = multi_emotion_voice_repository

    def create_voice(self,  entity: VoiceEntity):
        """创建新音色
        - 检查同名音色是否存在
        - 如果存在，抛出异常或返回错误
        - 调用 repository.create 插入数据库
        """

        voice = self.repository.get_by_name(entity.name, entity.tts_provider_id)
        if voice:
            return None
        # 手动将entity转化为po
        po = VoicePO(**entity.__dict__)
        res = self.repository.create(po)

        # res(po) --> entity
        data = {k: v for k, v in res.__dict__.items() if not k.startswith("_")}
        entity = VoiceEntity(**data)

        # 将po转化为entity
        return entity


    def get_voice(self, voice_id: int) -> VoiceEntity | None:
        """根据 ID 查询音色"""
        po = self.repository.get_by_id(voice_id)
        if not po:
            return None
        data = {k: v for k, v in po.__dict__.items() if not k.startswith("_")}
        res = VoiceEntity(**data)
        return res

    def get_all_voices(self,tts_provider_id: int) -> Sequence[VoiceEntity]:
        """获取所有音色列表"""
        pos = self.repository.get_all(tts_provider_id)
        # pos -> entities

        entities = [
            VoiceEntity(**{k: v for k, v in po.__dict__.items() if not k.startswith("_")})
            for po in pos
        ]
        return entities

    def update_voice(self, voice_id: int, data:dict) -> bool:
        """更新音色
        - 可以只更新部分字段
        - 检查同名冲突
        - 检查project_id不能改变
        """
        name = data["name"]
        tts_provider_id = data["tts_provider_id"]
        if self.repository.get_by_name(name, tts_provider_id) and self.repository.get_by_name(name,tts_provider_id).id != voice_id:
            return False
        po = self.repository.get_by_id(voice_id)
        # 防止改变project_id
        if po.tts_provider_id != tts_provider_id:
            return False
        self.repository.update(voice_id, data)
        return True

    def delete_voice(self, voice_id: int) -> bool:
        """删除音色,需要保证事务
        """

        res = self.repository.delete(voice_id)
        self.multi_emotion_voice_repository.delete_multi_emotion_voice_by_voice_id(voice_id)
        return res

    def export_voices(self, tts_provider_id: int, export_path: str) -> str:
        """导出音色库到zip文件
        - 获取所有音色
        - 将音色信息和对应的音频文件打包到zip
        - 返回zip文件路径
        """
        voices = self.get_all_voices(tts_provider_id)
        if not voices:
            return None

        # 确保导出目录存在
        os.makedirs(os.path.dirname(export_path) if os.path.dirname(export_path) else ".", exist_ok=True)

        # 创建zip文件
        with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 准备音色元数据
            voices_metadata = []
            
            for voice in voices:
                voice_data = {
                    "name": voice.name,
                    "description": voice.description,
                    "is_multi_emotion": voice.is_multi_emotion,
                    "reference_file": None
                }
                
                # 如果有参考音频文件，添加到zip
                if voice.reference_path and os.path.exists(voice.reference_path):
                    # 保持原文件名
                    file_name = os.path.basename(voice.reference_path)
                    # 使用音色名称作为子目录，避免文件名冲突
                    archive_path = f"voices/{voice.name}/{file_name}"
                    zipf.write(voice.reference_path, archive_path)
                    voice_data["reference_file"] = archive_path
                
                voices_metadata.append(voice_data)
            
            # 写入元数据文件
            metadata_json = json.dumps(voices_metadata, ensure_ascii=False, indent=2)
            zipf.writestr("voices_metadata.json", metadata_json)
        
        return export_path

    def import_voices(self, tts_provider_id: int, zip_path: str, target_dir: str) -> Tuple[int, int, List[str]]:
        """从zip文件导入音色库
        递归查找所有音频文件，用文件名（去扩展名）作为音色名
        """
        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"zip文件不存在: {zip_path}")

        # 确保目标目录存在
        os.makedirs(target_dir, exist_ok=True)

        success_count = 0
        skipped_count = 0
        skipped_names: List[str] = []

        audio_extensions = {".wav", ".flac", ".mp3", ".ogg", ".m4a"}

        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                zipf.extractall(temp_dir)

            # 递归查找所有音频文件
            for root, dirs, files in os.walk(temp_dir):
                # 过滤掉 macOS 的隐藏目录
                dirs[:] = [d for d in dirs if not d.startswith('__') and not d.startswith('.')]

                for f in files:
                    # 跳过隐藏文件
                    if f.startswith('.'):
                        continue

                    # 检查是否是音频文件
                    file_ext = os.path.splitext(f)[1].lower()
                    if file_ext not in audio_extensions:
                        continue

                    # 用文件名（去扩展名）作为音色名
                    voice_name = os.path.splitext(f)[0]
                    audio_path = os.path.join(root, f)

                    # 检查是否已存在同名音色
                    existing = self.repository.get_by_name(voice_name, tts_provider_id)
                    if existing:
                        skipped_count += 1
                        skipped_names.append(voice_name)
                        continue

                    # 复制音频文件到目标目录
                    dest_file = os.path.join(target_dir, f"{voice_name}{file_ext}")
                    shutil.copy2(audio_path, dest_file)

                    entity = VoiceEntity(
                        name=voice_name,
                        tts_provider_id=tts_provider_id,
                        reference_path=dest_file,
                        description=None,
                        is_multi_emotion=0
                    )

                    po = VoicePO(**entity.__dict__)
                    self.repository.create(po)
                    success_count += 1

        return success_count, skipped_count, skipped_names

    def process_audio(self, dto: VoiceAudioProcessDTO) -> bool:
        """处理音色参考音频
        - 变速、音量调整
        - 裁剪/删除区间
        - 添加/裁剪末尾静音
        - 指定位置插入静音
        """
        audio_path = dto.audio_path
        if not os.path.exists(audio_path):
            raise FileNotFoundError(audio_path)
        
        processor = AudioProcessor(audio_path)
        
        start_ms = dto.start_ms
        end_ms = dto.end_ms
        speed = dto.speed
        volume = dto.volume
        current_ms = dto.current_ms
        silence_sec = dto.silence_sec
        
        # ---------- (1) 优先裁剪 ----------
        if start_ms is not None and end_ms is not None and end_ms > start_ms:
            processor.cut(start_ms, end_ms)
        
        # ---------- (2) 插入静音 ----------
        elif current_ms is not None and silence_sec is not None and silence_sec != 0:
            processor.insert_silence(current_ms, silence_sec)
        
        # ---------- (3) 末尾静音/裁剪 ----------
        elif current_ms is None and silence_sec is not None and silence_sec != 0:
            processor.append_silence(silence_sec)
        
        # ---------- (4) 音量 + 变速 ----------
        if speed != 1.0:
            processor.change_speed(speed)
        if volume != 1.0:
            processor.change_volume(volume)
        
        return True

    def copy_voice(self, source_voice_id: int, new_name: str, target_dir: str = None) -> VoiceEntity:
        """复制音色
        - 获取源音色信息
        - 复制音频文件到目标目录
        - 创建新音色记录
        - 返回新音色实体
        """
        # 获取源音色
        source_voice = self.get_voice(source_voice_id)
        if not source_voice:
            raise ValueError("源音色不存在")
        
        # 检查新名称是否已存在
        existing = self.repository.get_by_name(new_name, source_voice.tts_provider_id)
        if existing:
            raise ValueError(f"音色名称 '{new_name}' 已存在")
        
        new_reference_path = None
        
        # 处理音频文件复制
        if source_voice.reference_path and os.path.exists(source_voice.reference_path):
            # 确定目标目录
            if target_dir and target_dir.strip():
                dest_dir = target_dir.strip()
            else:
                # 使用源音频所在目录
                dest_dir = os.path.dirname(source_voice.reference_path)
            
            # 确保目标目录存在
            os.makedirs(dest_dir, exist_ok=True)
            
            # 获取源文件扩展名
            file_ext = os.path.splitext(source_voice.reference_path)[1]
            # 使用新音色名作为文件名
            new_file_name = f"{new_name}{file_ext}"
            new_reference_path = os.path.join(dest_dir, new_file_name)
            
            # 复制文件
            shutil.copy2(source_voice.reference_path, new_reference_path)
        
        # 创建新音色实体
        new_entity = VoiceEntity(
            name=new_name,
            tts_provider_id=source_voice.tts_provider_id,
            reference_path=new_reference_path,
            description=source_voice.description,
            is_multi_emotion=source_voice.is_multi_emotion
        )
        
        # 保存到数据库
        po = VoicePO(**new_entity.__dict__)
        res = self.repository.create(po)
        
        # 返回新建的音色实体
        data = {k: v for k, v in res.__dict__.items() if not k.startswith("_")}
        return VoiceEntity(**data)
