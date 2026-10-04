import math
import asyncio
import logging
import datetime
from typing import Dict, Any, List, Optional
from backend.memory.db import db_helper

logger = logging.getLogger("zauq.xp")


class XPManager:
    @staticmethod
    def calculate_level(xp: int) -> int:
        if xp <= 0:
            return 1
        return int(math.floor(math.sqrt(xp / 100))) + 1

    @staticmethod
    def _calculate_streak(existing: Dict[str, Any]) -> int:
        """Returns the updated streak_days based on last_active_date."""
        today = datetime.date.today()
        last_active_date = existing.get("last_active_date")
        current_streak = existing.get("streak_days", 0)

        if not last_active_date:
            return 1

        try:
            if isinstance(last_active_date, str):
                last_date = datetime.date.fromisoformat(last_active_date[:10])
            else:
                last_date = last_active_date

            delta = (today - last_date).days
            if delta == 0:
                # Same day... don't change streak
                return current_streak
            elif delta == 1:
                # Consecutive day... increment streak
                return current_streak + 1
            else:
                # Streak broken
                return 1
        except Exception:
            return 1

    async def award_xp(
        self, user_id: str, guild_id: str, display_name: Optional[str] = None,
        xp_amount: int = 1, stat_type: str = "message"
    ) -> Dict[str, Any]:
        if not db_helper.supabase or not user_id:
            return {}

        try:
            # Fetch existing stats using composite PK (user_id + guild_id)
            res = await asyncio.to_thread(
                lambda: db_helper.supabase.table("user_stats")
                    .select("*")
                    .eq("user_id", user_id)
                    .eq("guild_id", guild_id or "global")
                    .execute()
            )
            existing = res.data[0] if res.data else None

            now_iso = datetime.datetime.utcnow().isoformat()
            today_iso = datetime.date.today().isoformat()

            if existing:
                new_xp = existing.get("xp", 0) + xp_amount
                new_level = self.calculate_level(new_xp)
                new_streak = self._calculate_streak(existing)

                payload = {
                    "xp": new_xp,
                    "level": new_level,
                    "streak_days": new_streak,
                    "last_active_date": today_iso,
                    "last_active_at": now_iso,
                    "display_name": display_name or existing.get("display_name", "User"),
                }
                if stat_type == "message":
                    payload["messages_count"] = existing.get("messages_count", 0) + 1
                elif stat_type == "command":
                    payload["commands_used"] = existing.get("commands_used", 0) + 1
                elif stat_type == "trivia_correct":
                    payload["trivia_correct"] = existing.get("trivia_correct", 0) + 1
                    payload["trivia_played"] = existing.get("trivia_played", 0) + 1
                elif stat_type == "trivia_played":
                    payload["trivia_played"] = existing.get("trivia_played", 0) + 1

                up_res = await asyncio.to_thread(
                    lambda: db_helper.supabase.table("user_stats")
                        .update(payload)
                        .eq("user_id", user_id)
                        .eq("guild_id", guild_id or "global")
                        .execute()
                )
                return up_res.data[0] if up_res.data else payload
            else:
                new_level = self.calculate_level(xp_amount)
                payload = {
                    "user_id": user_id,
                    "guild_id": guild_id or "global",
                    "display_name": display_name or "User",
                    "xp": xp_amount,
                    "level": new_level,
                    "streak_days": 1,
                    "last_active_date": today_iso,
                    "last_active_at": now_iso,
                    "messages_count": 1 if stat_type == "message" else 0,
                    "commands_used": 1 if stat_type == "command" else 0,
                    "trivia_correct": 1 if stat_type == "trivia_correct" else 0,
                    "trivia_played": 1 if "trivia" in stat_type else 0,
                }
                in_res = await asyncio.to_thread(
                    lambda: db_helper.supabase.table("user_stats").insert(payload).execute()
                )
                return in_res.data[0] if in_res.data else payload

        except Exception as e:
            logger.error(f"Failed to award XP to user {user_id} in guild {guild_id}: {e}")
            return {}

    async def get_user_rank(self, user_id: str, guild_id: Optional[str] = None) -> Dict[str, Any]:
        if not db_helper.supabase:
            return {"xp": 0, "level": 1, "rank": 1}

        try:
            res = await asyncio.to_thread(
                lambda: db_helper.supabase.table("user_stats")
                    .select("*")
                    .eq("user_id", user_id)
                    .eq("guild_id", guild_id or "global")
                    .execute()
            )
            if not res.data:
                return {"xp": 0, "level": 1, "rank": 1, "display_name": "User"}

            user_data = res.data[0]
            user_xp = user_data.get("xp", 0)

            # Count users with higher XP in the same guild
            query = (
                db_helper.supabase.table("user_stats")
                    .select("user_id", count="exact")
                    .gt("xp", user_xp)
            )
            if guild_id and guild_id != "global":
                query = query.eq("guild_id", guild_id)

            rank_res = await asyncio.to_thread(lambda: query.execute())
            rank = (rank_res.count or 0) + 1

            return {
                "user_id": user_id,
                "display_name": user_data.get("display_name", "User"),
                "xp": user_xp,
                "level": user_data.get("level", 1),
                "rank": rank,
                "streak_days": user_data.get("streak_days", 0),
                "messages_count": user_data.get("messages_count", 0),
                "commands_used": user_data.get("commands_used", 0),
                "trivia_correct": user_data.get("trivia_correct", 0),
            }
        except Exception as e:
            logger.error(f"Error fetching user rank for {user_id}: {e}")
            return {"xp": 0, "level": 1, "rank": 1}

    async def get_leaderboard(self, guild_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        if not db_helper.supabase:
            return []

        try:
            query = db_helper.supabase.table("user_stats").select("*")
            if guild_id and guild_id != "global":
                query = query.eq("guild_id", guild_id)
            res = await asyncio.to_thread(
                lambda: query.order("xp", desc=True).limit(limit).execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"Error fetching leaderboard: {e}")
            return []


xp_manager = XPManager()
