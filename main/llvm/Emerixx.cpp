//===--- Emerixx.cpp - Emerixx ToolChain Implementations --------*- C++ -*-===//
//
// Part of the LLVM Project, under the Apache License v2.0 with LLVM
// Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#include "Emerixx.h"
#include "CommonArgs.h"
#include "clang/Driver/Driver.h"
#include "clang/Driver/Options.h"
#include "llvm/Option/ArgList.h"

using namespace clang::driver;
using namespace clang::driver::toolchains;
using namespace clang;
using namespace llvm::opt;

Emerixx::Emerixx(const Driver &D, const llvm::Triple &Triple,
                 const ArgList &Args)
    : Linux(D, Triple, Args) {}

bool Emerixx::isPIEDefault(const ArgList &Args) const {
  // The emerixx kernel does not support PIE executables.
  return false;
}

std::string Emerixx::getMultiarchTriple(const Driver &D,
                                        const llvm::Triple &TargetTriple,
                                        StringRef SysRoot) const {
  // emerixx is not a multiarch system; libraries live directly in /usr/lib.
  return TargetTriple.str();
}