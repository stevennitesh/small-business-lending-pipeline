"""Resolve raw and manifest artifact stores for extraction flow stages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pipelines.flows.run_models import LocalRunContext
from pipelines.flows.run_setup import resolve_s3_bucket
from pipelines.storage.raw_artifacts import (
    LocalArtifactStore,
    LocalRawArtifactStore,
    S3ArtifactStore,
    S3RawArtifactStore,
    artifact_store_for_route,
    raw_artifact_store_for_route,
)


RawStoreFactory = Callable[
    [LocalRunContext, str],
    LocalRawArtifactStore | S3RawArtifactStore,
]
ArtifactStoreFactory = Callable[
    [LocalRunContext, str],
    LocalArtifactStore | S3ArtifactStore,
]
BucketResolver = Callable[[LocalRunContext], str | None]


@dataclass(frozen=True)
class ExtractionArtifactStores:
    """Artifact stores and bucket used by source extraction."""

    bucket: str
    raw_store: LocalRawArtifactStore | S3RawArtifactStore
    manifest_store: LocalArtifactStore | S3ArtifactStore | None


def resolve_extraction_artifact_stores(
    context: LocalRunContext,
    *,
    default_bucket: str,
    raw_artifact_store_factory: RawStoreFactory | None = None,
    artifact_store_factory: ArtifactStoreFactory | None = None,
    s3_bucket_resolver: BucketResolver | None = None,
) -> ExtractionArtifactStores:
    """Resolve all extraction artifact stores for the active run route."""
    bucket = resolve_extraction_bucket(
        context,
        default_bucket=default_bucket,
        s3_bucket_resolver=s3_bucket_resolver,
    )
    return ExtractionArtifactStores(
        bucket=bucket,
        raw_store=resolve_raw_artifact_store(
            context,
            bucket,
            raw_artifact_store_factory=raw_artifact_store_factory,
        ),
        manifest_store=resolve_manifest_artifact_store(
            context,
            bucket,
            artifact_store_factory=artifact_store_factory,
        ),
    )


def resolve_extraction_bucket(
    context: LocalRunContext,
    *,
    default_bucket: str,
    s3_bucket_resolver: BucketResolver | None = None,
) -> str:
    """Resolve extraction bucket from context/env with a route-specific fallback."""
    return (s3_bucket_resolver or resolve_s3_bucket)(context) or default_bucket


def resolve_raw_artifact_store(
    context: LocalRunContext,
    bucket: str,
    *,
    raw_artifact_store_factory: RawStoreFactory | None = None,
) -> LocalRawArtifactStore | S3RawArtifactStore:
    """Return an injectable or route-specific raw artifact store."""
    if raw_artifact_store_factory is not None:
        return raw_artifact_store_factory(context, bucket)
    return raw_artifact_store_for_route(
        cloud_route=context.is_cloud_route,
        data_root=context.data_root,
        bucket=bucket,
    )


def resolve_manifest_artifact_store(
    context: LocalRunContext,
    bucket: str,
    *,
    artifact_store_factory: ArtifactStoreFactory | None = None,
) -> LocalArtifactStore | S3ArtifactStore | None:
    """Return a manifest artifact store only for cloud extraction routes."""
    if not context.is_cloud_route:
        return None
    if artifact_store_factory is not None:
        return artifact_store_factory(context, bucket)
    return artifact_store_for_route(
        cloud_route=context.is_cloud_route,
        data_root=context.data_root,
        bucket=bucket,
    )
