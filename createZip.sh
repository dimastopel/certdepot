#!/bin/bash

pushd certs
zip -9 $1 $2 $3
popd

