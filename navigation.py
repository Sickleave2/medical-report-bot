# navigation.py
from aiogram.dispatcher import FSMContext

class Navigation:
    @staticmethod
    async def push_state(state: FSMContext, new_state: str):
        """إضافة حالة جديدة إلى المكدس"""
        stack = await state.get_data('nav_stack', [])
        stack.append(new_state)
        await state.update_data(nav_stack=stack)

    @staticmethod
    async def pop_state(state: FSMContext) -> str:
        """إزالة آخر حالة وإرجاعها"""
        stack = await state.get_data('nav_stack', [])
        if stack:
            return stack.pop()
        return None

    @staticmethod
    async def go_back(state: FSMContext, current_state: str) -> str:
        """الرجوع للخلف: يزيل الحالة الحالية ويعيد الحالة السابقة"""
        stack = await state.get_data('nav_stack', [])
        if not stack:
            return None
        # الحالة السابقة هي آخر عنصر في المكدس
        previous = stack[-1]
        # لا نزيلها هنا، بل سنقوم بالرجوع إليها
        return previous

    @staticmethod
    async def reset(state: FSMContext):
        """مسح المكدس"""
        await state.update_data(nav_stack=[])
