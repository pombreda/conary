Summary: test postscript failure
Name: failpost
Version: 1.0
Release: 1
ExclusiveOs: Linux
BuildRoot: %{_tmppath}/%{name}-root
BuildArch: noarch
Group: something
License: something
Requires: aaa_first
Provides: problem

%description
junk

%prep

%build

%install
mkdir -p $RPM_BUILD_ROOT/dummy
echo > $RPM_BUILD_ROOT/dummy/file

%clean
rm -rf $RPM_BUILD_ROOT

%post
echo 'this post script fails'
exit 1

%files
%attr(-,root,root) /dummy/file
