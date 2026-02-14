/* We are piggybacking on linux configs */

#ifdef GNU_USER_TARGET_OS_CPP_BUILTINS
#undef GNU_USER_TARGET_OS_CPP_BUILTINS
#endif

#define GNU_USER_TARGET_OS_CPP_BUILTINS()			\
    do {							\
	builtin_define_std ("__emerixx__");			\
	builtin_define_std ("__unix__");			\
	builtin_assert ("system=emerixx");			\
	builtin_assert ("system=unix");				\
	builtin_assert ("system=posix");			\
    } while (0)

#ifdef TARGET_LIBC_HAS_FUNCTION
#undef TARGET_LIBC_HAS_FUNCTION
#endif

#ifdef TARGET_FORTIFY_SOURCE_DEFAULT_LEVEL
#undef TARGET_FORTIFY_SOURCE_DEFAULT_LEVEL
#endif
