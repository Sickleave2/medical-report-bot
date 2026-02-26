# navigation.py
from aiogram.dispatcher import FSMContext

class Navigation:
    @staticmethod
    async def push_state(state: FSMContext, new_state: str):
        """إضافة حالة جديدة إلى المكدس"""
        data = await state.get_data()
        stack = data.get('nav_stack', [])
        stack.append(new_state)
        await state.update_data(nav_stack=stack)

    @staticmethod
    async def pop_state(state: FSMContext) -> str:
        """إزالة آخر حالة وإرجاعها"""
        data = await state.get_data()
        stack = data.get('nav_stack', [])
        if stack:
            return stack.pop()
        return None

    @staticmethod
    async def go_back(state: FSMContext, current_state: str) -> str:
        """الرجوع للخلف: يزيل الحالة الحالية ويعيد الحالة السابقة"""
        data = await state.get_data()
        stack = data.get('nav_stack', [])
        if not stack:
            return None
        # الحالة السابقة هي آخر عنصر في المكدس
        return stack[-1]

    @staticmethod
    async def reset(state: FSMContext):
        """مسح المكدس"""
        await state.update_data(nav_stack=[])
